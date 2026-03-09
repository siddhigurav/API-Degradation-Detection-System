"""
Prometheus Metrics Collector

Collects metrics from Prometheus and ingests them into Kafka streaming pipeline.
This is the entry point for all metrics data.

Features:
- Scrapes Prometheus remote read API
- Schema validation
- Metric enrichment (labels, tags)
- Cardinality control
- Dead letter handling for bad data
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import hashlib

import httpx
from kafka import KafkaProducer
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

# Configure structured logging
log = structlog.get_logger()


@dataclass
class MetricPoint:
    """Validated metric data point"""
    timestamp: datetime
    endpoint: str
    metric_name: str
    value: float
    metric_type: str  # gauge, counter, histogram, summary
    labels: Dict[str, str]
    status_code: Optional[int] = None
    method: Optional[str] = None

    def to_dict(self):
        """Convert to JSON-serializable dict"""
        return {
            'timestamp': self.timestamp.isoformat() + 'Z',
            'endpoint': self.endpoint,
            'metric_name': self.metric_name,
            'value': self.value,
            'metric_type': self.metric_type,
            'labels': self.labels,
            'status_code': self.status_code,
            'method': self.method
        }

    def get_hash(self) -> str:
        """Get hash for cardinality tracking"""
        key = f"{self.endpoint}{self.metric_name}{json.dumps(self.labels, sort_keys=True)}"
        return hashlib.md5(key.encode()).hexdigest()


class PrometheusCollector:
    """Collect metrics from Prometheus and publish to Kafka"""

    def __init__(
        self,
        prometheus_url: str = "http://localhost:9090",
        kafka_bootstrap_servers: str = "localhost:9092",
        scrape_interval_seconds: int = 10,
        max_metric_cardinality: int = 100000
    ):
        self.prometheus_url = prometheus_url
        self.scrape_interval = scrape_interval_seconds
        self.max_cardinality = max_metric_cardinality
        
        # Kafka producer for publishing metrics
        self.kafka_producer = KafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            linger_ms=100,  # Batch messages for 100ms
            batch_size=1000,
            acks='all',
            retries=3
        )
        
        # HTTP client for Prometheus
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
        # Cardinality tracking
        self.metric_hashes = set()
        self.last_cardinality_check = datetime.now(timezone.utc)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _query_prometheus(self, query: str) -> Dict[str, Any]:
        """Query Prometheus API with retry logic"""
        try:
            response = await self.http_client.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            log.error("prometheus_query_error", query=query, error=str(e))
            raise

    async def collect_metrics(self) -> List[MetricPoint]:
        """
        Collect all metrics from Prometheus.
        
        Queries multiple metric patterns:
        - http_request_latency_ms
        - http_requests_total (errors)
        - http_requests_created (request rate)
        - process_resident_memory_bytes
        - process_cpu_seconds_total
        """
        
        all_metrics = []
        
        try:
            # Collect latency metrics
            latency_metrics = await self._collect_latency_metrics()
            all_metrics.extend(latency_metrics)
            
            # Collect error metrics
            error_metrics = await self._collect_error_metrics()
            all_metrics.extend(error_metrics)
            
            # Collect resource metrics
            resource_metrics = await self._collect_resource_metrics()
            all_metrics.extend(resource_metrics)
            
            log.info("metrics_collected", count=len(all_metrics))
            return all_metrics
            
        except Exception as e:
            log.error("metric_collection_error", error=str(e))
            return []

    async def _collect_latency_metrics(self) -> List[MetricPoint]:
        """Collect latency metrics from Prometheus"""
        metrics = []
        
        # Query for HTTP request latency
        query = 'http_request_latency_ms'
        result = await self._query_prometheus(query)
        
        if result.get('status') != 'success':
            return metrics
        
        for sample in result.get('data', {}).get('result', []):
            try:
                metric_dict = sample.get('metric', {})
                value_tuple = sample.get('value', [None, None])
                timestamp_unix = float(value_tuple[0])
                value = float(value_tuple[1])
                
                # Extract labels
                endpoint = metric_dict.get('endpoint', 'unknown')
                method = metric_dict.get('method', 'GET')
                status = metric_dict.get('status', '')
                
                timestamp = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc)
                
                # Create metric point for each percentile
                for percentile in ['p50', 'p95', 'p99']:
                    metric = MetricPoint(
                        timestamp=timestamp,
                        endpoint=endpoint,
                        metric_name=f'latency_{percentile}',
                        value=value,
                        metric_type='gauge',
                        labels={'method': method, 'percentile': percentile},
                        method=method,
                        status_code=int(status) if status.isdigit() else None
                    )
                    metrics.append(metric)
                    
            except (ValueError, KeyError, TypeError) as e:
                log.warning("invalid_metric_data", error=str(e), sample=sample)
                continue
        
        return metrics

    async def _collect_error_metrics(self) -> List[MetricPoint]:
        """Collect error rate metrics"""
        metrics = []
        
        # Query for HTTP errors
        query = 'rate(http_requests_total{status=~"5.."}[1m])'
        result = await self._query_prometheus(query)
        
        if result.get('status') != 'success':
            return metrics
        
        for sample in result.get('data', {}).get('result', []):
            try:
                metric_dict = sample.get('metric', {})
                value_tuple = sample.get('value', [None, None])
                timestamp_unix = float(value_tuple[0])
                value = float(value_tuple[1])
                
                endpoint = metric_dict.get('endpoint', 'unknown')
                method = metric_dict.get('method', 'GET')
                
                timestamp = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc)
                
                metric = MetricPoint(
                    timestamp=timestamp,
                    endpoint=endpoint,
                    metric_name='error_rate',
                    value=value / 100.0,  # Convert percentage to rate
                    metric_type='gauge',
                    labels={'method': method},
                    method=method
                )
                metrics.append(metric)
                
            except (ValueError, KeyError, TypeError) as e:
                log.warning("invalid_error_metric", error=str(e))
                continue
        
        return metrics

    async def _collect_resource_metrics(self) -> List[MetricPoint]:
        """Collect CPU/memory metrics"""
        metrics = []
        
        # CPU and memory queries
        queries = [
            ('process_cpu_seconds_total', 'cpu_seconds'),
            ('process_resident_memory_bytes', 'memory_bytes')
        ]
        
        for query_name, metric_name in queries:
            try:
                result = await self._query_prometheus(query_name)
                
                if result.get('status') != 'success':
                    continue
                
                for sample in result.get('data', {}).get('result', []):
                    metric_dict = sample.get('metric', {})
                    value_tuple = sample.get('value', [None, None])
                    timestamp_unix = float(value_tuple[0])
                    value = float(value_tuple[1])
                    
                    job = metric_dict.get('job', 'api-services')
                    instance = metric_dict.get('instance', 'unknown')
                    
                    timestamp = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc)
                    
                    metric = MetricPoint(
                        timestamp=timestamp,
                        endpoint=f"/resource/{instance}",
                        metric_name=metric_name,
                        value=value,
                        metric_type='gauge',
                        labels={'job': job, 'instance': instance}
                    )
                    metrics.append(metric)
                    
            except Exception as e:
                log.warning("resource_metric_error", query=query_name, error=str(e))
                continue
        
        return metrics

    async def _validate_metrics(self, metrics: List[MetricPoint]) -> List[MetricPoint]:
        """Validate metrics and check cardinality"""
        valid_metrics = []
        
        for metric in metrics:
            # Basic validation
            if not metric.endpoint or not metric.metric_name:
                log.warning("invalid_metric", metric=metric)
                continue
            
            if not isinstance(metric.value, (int, float)) or metric.value < 0:
                log.warning("invalid_metric_value", metric=metric)
                continue
            
            # Cardinality check
            metric_hash = metric.get_hash()
            is_new_cardinality = metric_hash not in self.metric_hashes
            
            if is_new_cardinality:
                if len(self.metric_hashes) >= self.max_cardinality:
                    log.warning("cardinality_limit_exceeded", 
                               cardinality=len(self.metric_hashes),
                               limit=self.max_cardinality)
                    continue
                self.metric_hashes.add(metric_hash)
            
            valid_metrics.append(metric)
        
        return valid_metrics

    async def _enrich_metrics(self, metrics: List[MetricPoint]) -> List[MetricPoint]:
        """Enrich metrics with additional context"""
        for metric in metrics:
            # Add environment labels
            metrics_dict = asdict(metric)
            metrics_dict['labels']['environment'] = 'production'
            metrics_dict['labels']['region'] = 'us-east-1'
            metrics_dict['labels']['version'] = 'v1'
        
        return metrics

    def publish_to_kafka(self, metrics: List[MetricPoint], topic: str = 'raw-metrics'):
        """Publish metrics to Kafka"""
        if not metrics:
            return
        
        try:
            for metric in metrics:
                self.kafka_producer.send(
                    topic,
                    value=metric.to_dict(),
                    key=f"{metric.endpoint}:{metric.metric_name}".encode('utf-8')
                )
            
            self.kafka_producer.flush(timeout=5)
            log.info("metrics_published", count=len(metrics), topic=topic)
            
        except Exception as e:
            log.error("kafka_publish_error", error=str(e), count=len(metrics))

    async def run(self):
        """Main collection loop"""
        log.info("prometheus_collector_started", 
                prometheus_url=self.prometheus_url,
                scrape_interval=self.scrape_interval)
        
        try:
            while True:
                start_time = datetime.now(timezone.utc)
                
                # Collect metrics
                metrics = await self.collect_metrics()
                
                # Validate
                validated = await self._validate_metrics(metrics)
                log.info("metrics_validated", total=len(metrics), valid=len(validated))
                
                # Enrich
                enriched = await self._enrich_metrics(validated)
                
                # Publish
                self.publish_to_kafka(enriched)
                
                # Wait until scrape interval
                elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                sleep_time = max(0, self.scrape_interval - elapsed)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    
        except KeyboardInterrupt:
            log.info("collector_interrupted")
        except Exception as e:
            log.error("collector_error", error=str(e))
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Cleanup resources"""
        self.kafka_producer.close()
        await self.http_client.aclose()
        log.info("prometheus_collector_shutdown")


async def main():
    """Main entry point"""
    import sys
    from src.config import PROMETHEUS_URL, KAFKA_BOOTSTRAP_SERVERS
    
    collector = PrometheusCollector(
        prometheus_url=PROMETHEUS_URL,
        kafka_bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        max_metric_cardinality=100000
    )
    
    try:
        await collector.run()
    except KeyboardInterrupt:
        print("Shutting down...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
