"""
Feature Extraction Service - Phase 1

Consumes raw metrics from Prometheus via Kafka.
Computes rolling window statistics and features for ML models.

Features:
- Rolling window aggregation (1m, 5m, 15m, 1h)
- Trend detection (increasing/decreasing/stable)
- Baseline computation and drift detection
- Feature vector creation for ML models
- Publishes to feature-store Kafka topic
"""

import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from kafka import KafkaConsumer, KafkaProducer
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger()


@dataclass
class WindowStats:
    """Statistics for a time window"""
    count: int
    mean: float
    stddev: float
    min_val: float
    max_val: float
    p50: float
    p95: float
    p99: float
    
    def to_dict(self):
        return {
            'count': self.count,
            'mean': self.mean,
            'stddev': self.stddev,
            'min': self.min_val,
            'max': self.max_val,
            'p50': self.p50,
            'p95': self.p95,
            'p99': self.p99
        }


class RollingWindowBuffer:
    """Maintains rolling buffers for time-windowed aggregation"""
    
    WINDOWS = [60, 300, 900, 3600]  # 1m, 5m, 15m, 1h seconds
    
    def __init__(self):
        # endpoint -> metric_name -> window_seconds -> deque of (timestamp, value)
        self.buffers: Dict[str, Dict[str, Dict[int, deque]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(deque))
        )
        self.last_aggregation_time = {}
    
    def add_value(self, endpoint: str, metric_name: str, timestamp: float, value: float):
        """Add a value to all window buffers"""
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        
        for window_sec in self.WINDOWS:
            buffer = self.buffers[endpoint][metric_name][window_sec]
            buffer.append((timestamp, value))
            
            # Prune old entries
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_sec)
            cutoff_ts = cutoff.timestamp()
            
            while buffer and buffer[0][0] < cutoff_ts:
                buffer.popleft()
    
    def get_stats(self, endpoint: str, metric_name: str, window_seconds: int) -> Optional[WindowStats]:
        """Get statistics for a window"""
        buffer = self.buffers[endpoint][metric_name].get(window_seconds, deque())
        
        if len(buffer) < 2:
            return None
        
        values = [v for _, v in buffer]
        
        return WindowStats(
            count=len(values),
            mean=float(np.mean(values)),
            stddev=float(np.std(values)),
            min_val=float(np.min(values)),
            max_val=float(np.max(values)),
            p50=float(np.percentile(values, 50)),
            p95=float(np.percentile(values, 95)),
            p99=float(np.percentile(values, 99))
        )
    
    def cleanup(self, endpoint: str, metric_name: str):
        """Remove old entries from all buffers"""
        now_ts = datetime.now(timezone.utc).timestamp()
        
        for window_sec in self.WINDOWS:
            buffer = self.buffers[endpoint][metric_name][window_sec]
            while buffer and (now_ts - buffer[0][0]) > window_sec:
                buffer.popleft()


class FeatureExtractionService:
    """Extract ML features from raw metrics"""
    
    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        consumer_group: str = "feature_engineering_service"
    ):
        self.consumer = KafkaConsumer(
            'raw-metrics',
            bootstrap_servers=kafka_bootstrap_servers,
            group_id=consumer_group,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            max_poll_records=1000,
            session_timeout_ms=30000,
            enable_auto_commit=True
        )
        
        self.producer = KafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            retries=3
        )
        
        self.buffers = RollingWindowBuffer()
        self.baseline_stats = defaultdict(dict)  # endpoint -> metric_name -> baseline
        
        log.info("feature_extraction_service_initialized")
    
    def process_raw_metric(self, metric_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process a raw metric and extract features
        
        Returns list of feature windows for different aggregation levels
        """
        try:
            endpoint = metric_data['endpoint']
            metric_name = metric_data['metric_name']
            value = float(metric_data['value'])
            timestamp_str = metric_data['timestamp']
            
            # Parse timestamp
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str[:-1] + '+00:00'
            dt = datetime.fromisoformat(timestamp_str)
            timestamp = dt.timestamp()
            
            # Add to buffers
            self.buffers.add_value(endpoint, metric_name, timestamp, value)
            
            # Extract features for all windows
            features_list = []
            
            for window_sec in RollingWindowBuffer.WINDOWS:
                stats = self.buffers.get_stats(endpoint, metric_name, window_sec)
                
                if stats is None:
                    continue
                
                window_name = f"{window_sec // 60}m" if window_sec < 3600 else "1h"
                
                features = {
                    'timestamp': dt.isoformat() + 'Z',
                    'endpoint': endpoint,
                    'metric_name': metric_name,
                    'window': window_name,
                    'window_seconds': window_sec,
                    'stats': stats.to_dict(),
                    'features': self._extract_features(
                        endpoint, metric_name, window_sec, stats
                    )
                }
                
                features_list.append(features)
            
            return features_list
            
        except Exception as e:
            log.error("metric_processing_error", error=str(e), metric=metric_data)
            return []
    
    def _extract_features(
        self,
        endpoint: str,
        metric_name: str,
        window_sec: int,
        stats: WindowStats
    ) -> Dict[str, float]:
        """Extract ML features from statistics"""
        
        features = {
            'mean': stats.mean,
            'stddev': stats.stddev,
            'min': stats.min_val,
            'max': stats.max_val,
            'range': stats.max_val - stats.min_val,
            'p50': stats.p50,
            'p95': stats.p95,
            'p99': stats.p99,
            'cv': stats.stddev / stats.mean if stats.mean > 0 else 0,  # Coefficient of variation
        }
        
        # Trend features
        baseline = self.baseline_stats.get(endpoint, {}).get(metric_name, {})
        if baseline:
            baseline_mean = baseline.get('mean', stats.mean)
            baseline_stddev = baseline.get('stddev', stats.stddev)
            
            # Z-score
            if baseline_stddev > 0:
                features['z_score'] = (stats.mean - baseline_mean) / baseline_stddev
            else:
                features['z_score'] = 0
            
            # Change percentage
            if baseline_mean > 0:
                features['change_pct'] = (stats.mean - baseline_mean) / baseline_mean
            else:
                features['change_pct'] = 0
        
        return features
    
    def update_baseline(self, endpoint: str, metric_name: str, stats: WindowStats):
        """Update baseline statistics (online learning)"""
        
        baseline_key = f"{endpoint}:{metric_name}"
        
        if baseline_key not in self.baseline_stats:
            # First time seeing this metric
            self.baseline_stats[endpoint][metric_name] = {
                'mean': stats.mean,
                'stddev': stats.stddev,
                'count': 1
            }
        else:
            # Update using exponential weighted moving average (alpha=0.1)
            alpha = 0.1
            old_stats = self.baseline_stats[endpoint][metric_name]
            
            old_stats['mean'] = (1 - alpha) * old_stats['mean'] + alpha * stats.mean
            old_stats['stddev'] = (1 - alpha) * old_stats['stddev'] + alpha * stats.stddev
            old_stats['count'] += 1
    
    def publish_features(self, features_list: List[Dict[str, Any]], topic: str = 'feature-store'):
        """Publish extracted features to Kafka"""
        try:
            for features in features_list:
                self.producer.send(
                    topic,
                    value=features,
                    key=f"{features['endpoint']}:{features['metric_name']}".encode('utf-8')
                )
            
            if features_list:
                self.producer.flush(timeout=5)
                log.info("features_published", count=len(features_list), topic=topic)
                
        except Exception as e:
            log.error("feature_publish_error", error=str(e))
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def run(self):
        """Main processing loop"""
        log.info("feature_extraction_started")
        
        batch_count = 0
        feature_batch = []
        
        try:
            for message in self.consumer:
                try:
                    metric_data = message.value
                    
                    # Process metric
                    features_list = self.process_raw_metric(metric_data)
                    feature_batch.extend(features_list)
                    
                    # Batch publish every 1000 messages
                    batch_count += 1
                    if batch_count >= 1000:
                        self.publish_features(feature_batch)
                        feature_batch = []
                        batch_count = 0
                        
                        # Update baselines periodically
                        for features in feature_batch:
                            stats_dict = features['stats']
                            stats = WindowStats(
                                count=stats_dict['count'],
                                mean=stats_dict['mean'],
                                stddev=stats_dict['stddev'],
                                min_val=stats_dict['min'],
                                max_val=stats_dict['max'],
                                p50=stats_dict['p50'],
                                p95=stats_dict['p95'],
                                p99=stats_dict['p99']
                            )
                            self.update_baseline(features['endpoint'], features['metric_name'], stats)
                    
                except Exception as e:
                    log.error("message_processing_error", error=str(e))
                    continue
                    
        except KeyboardInterrupt:
            log.info("feature_extraction_interrupted")
        finally:
            # Publish remaining batch
            if feature_batch:
                self.publish_features(feature_batch)
            self.shutdown()
    
    def shutdown(self):
        """Cleanup"""
        self.producer.close()
        self.consumer.close()
        log.info("feature_extraction_shutdown")


async def main():
    """Main entry point"""
    service = FeatureExtractionService(
        kafka_bootstrap_servers="localhost:9092"
    )
    
    try:
        service.run()
    except KeyboardInterrupt:
        print("Shutting down...")
    except Exception as e:
        log.error("service_error", error=str(e))


if __name__ == '__main__':
    main()
