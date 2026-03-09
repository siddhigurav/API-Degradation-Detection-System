"""
Monitoring, Observability & Metrics

Implements:
- Prometheus metrics export
- Request/response logging
- Performance monitoring
- Anomaly metrics
- Alert pipeline metrics
- RCA metrics
"""

from datetime import datetime
from typing import Dict, List, Optional
import time
import structlog
from enum import Enum

log = structlog.get_logger()


class MetricCounter:
    """Counter metric"""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.value = 0
        self.labels: Dict[str, int] = {}
    
    def increment(self, labels: Dict[str, str] = None, amount: int = 1):
        """Increment counter"""
        self.value += amount
        
        if labels:
            key = ", ".join(f"{k}={v}" for k, v in labels.items())
            self.labels[key] = self.labels.get(key, 0) + amount
    
    def to_prometheus(self) -> str:
        """Convert to Prometheus format"""
        lines = [f"# HELP {self.name} {self.description}"]
        lines.append(f"# TYPE {self.name} counter")
        lines.append(f"{self.name} {self.value}")
        
        for labels, val in self.labels.items():
            lines.append(f"{self.name}{{{labels}}} {val}")
        
        return "\n".join(lines)


class MetricGauge:
    """Gauge metric (current value)"""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.value = 0
        self.labels: Dict[str, float] = {}
    
    def set(self, value: float, labels: Dict[str, str] = None):
        """Set gauge value"""
        self.value = value
        
        if labels:
            key = ", ".join(f"{k}={v}" for k, v in labels.items())
            self.labels[key] = value
    
    def to_prometheus(self) -> str:
        """Convert to Prometheus format"""
        lines = [f"# HELP {self.name} {self.description}"]
        lines.append(f"# TYPE {self.name} gauge")
        lines.append(f"{self.name} {self.value}")
        
        for labels, val in self.labels.items():
            lines.append(f"{self.name}{{{labels}}} {val}")
        
        return "\n".join(lines)


class MetricHistogram:
    """Histogram metric"""
    
    def __init__(self, name: str, description: str = "", buckets: List[float] = None):
        self.name = name
        self.description = description
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self.observations: List[float] = []
    
    def observe(self, value: float):
        """Record observation"""
        self.observations.append(value)
    
    def get_stats(self) -> Dict:
        """Get histogram statistics"""
        if not self.observations:
            return {
                "count": 0,
                "sum": 0,
                "min": 0,
                "max": 0,
                "avg": 0,
                "p50": 0,
                "p95": 0,
                "p99": 0
            }
        
        sorted_obs = sorted(self.observations)
        count = len(sorted_obs)
        
        return {
            "count": count,
            "sum": sum(sorted_obs),
            "min": sorted_obs[0],
            "max": sorted_obs[-1],
            "avg": sum(sorted_obs) / count,
            "p50": sorted_obs[int(count * 0.50)],
            "p95": sorted_obs[int(count * 0.95)],
            "p99": sorted_obs[int(count * 0.99)]
        }
    
    def to_prometheus(self) -> str:
        """Convert to Prometheus format"""
        lines = [f"# HELP {self.name} {self.description}"]
        lines.append(f"# TYPE {self.name} histogram")
        
        stats = self.get_stats()
        for bucket in self.buckets:
            count = sum(1 for obs in self.observations if obs <= bucket)
            lines.append(f"{self.name}_bucket{{le=\"{bucket}\"}} {count}")
        
        lines.append(f"{self.name}_bucket{{le=\"+Inf\"}} {len(self.observations)}")
        lines.append(f"{self.name}_sum {stats['sum']}")
        lines.append(f"{self.name}_count {stats['count']}")
        
        return "\n".join(lines)


class ApplicationMetrics:
    """Application-level metrics"""
    
    def __init__(self):
        """Initialize metrics"""
        
        # API Metrics
        self.api_requests = MetricCounter(
            "api_requests_total",
            "Total API requests"
        )
        self.api_latency = MetricHistogram(
            "api_latency_seconds",
            "API request latency"
        )
        self.api_errors = MetricCounter(
            "api_errors_total",
            "Total API errors"
        )
        
        # Anomaly Detection Metrics
        self.anomalies_detected = MetricCounter(
            "anomalies_detected_total",
            "Total anomalies detected"
        )
        self.anomaly_latency = MetricHistogram(
            "anomaly_detection_latency_seconds",
            "Anomaly detection latency"
        )
        
        # Alert Metrics
        self.alerts_created = MetricCounter(
            "alerts_created_total",
            "Total alerts created"
        )
        self.alerts_by_severity = MetricGauge(
            "alerts_by_severity",
            "Alerts by severity"
        )
        self.alert_dedup_saved = MetricCounter(
            "alert_dedup_saved_total",
            "Alerts saved by deduplication"
        )
        
        # RCA Metrics
        self.rca_analyses = MetricCounter(
            "rca_analyses_total",
            "Total RCA analyses"
        )
        self.rca_latency = MetricHistogram(
            "rca_latency_seconds",
            "RCA analysis latency"
        )
        self.rca_avg_confidence = MetricGauge(
            "rca_avg_confidence",
            "Average RCA confidence"
        )
        
        # Kafka Metrics
        self.kafka_messages_processed = MetricCounter(
            "kafka_messages_processed_total",
            "Kafka messages processed"
        )
        self.kafka_lag = MetricGauge(
            "kafka_consumer_lag",
            "Kafka consumer lag"
        )
        
        # Resource Metrics
        self.db_connections = MetricGauge(
            "db_connections",
            "Active database connections"
        )
        self.cache_hits = MetricCounter(
            "cache_hits_total",
            "Cache hits"
        )
        self.cache_misses = MetricCounter(
            "cache_misses_total",
            "Cache misses"
        )
    
    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus format"""
        metrics = [
            self.api_requests.to_prometheus(),
            self.api_latency.to_prometheus(),
            self.api_errors.to_prometheus(),
            self.anomalies_detected.to_prometheus(),
            self.anomaly_latency.to_prometheus(),
            self.alerts_created.to_prometheus(),
            self.alerts_by_severity.to_prometheus(),
            self.rca_analyses.to_prometheus(),
            self.rca_latency.to_prometheus(),
            self.kafka_messages_processed.to_prometheus(),
        ]
        
        return "\n\n".join(metrics)
    
    def get_summary(self) -> dict:
        """Get metrics summary"""
        return {
            "api_requests": self.api_requests.value,
            "api_errors": self.api_errors.value,
            "anomalies_detected": self.anomalies_detected.value,
            "alerts_created": self.alerts_created.value,
            "rca_analyses": self.rca_analyses.value,
            "kafka_messages": self.kafka_messages_processed.value,
            "latency_stats": {
                "api": self.api_latency.get_stats(),
                "anomaly_detection": self.anomaly_latency.get_stats(),
                "rca": self.rca_latency.get_stats()
            }
        }


class RequestLogger:
    """Request/response logging"""
    
    @staticmethod
    def log_request(
        method: str,
        path: str,
        client_id: str,
        headers: Dict = None
    ):
        """Log incoming request"""
        log.info(
            "request_received",
            method=method,
            path=path,
            client_id=client_id,
            timestamp=datetime.utcnow().isoformat()
        )
    
    @staticmethod
    def log_response(
        method: str,
        path: str,
        status_code: int,
        latency_ms: float,
        client_id: str = None
    ):
        """Log response"""
        level = "info" if status_code < 400 else "warning"
        
        log.log(
            level,
            "response_sent",
            method=method,
            path=path,
            status_code=status_code,
            latency_ms=latency_ms,
            client_id=client_id,
            timestamp=datetime.utcnow().isoformat()
        )
    
    @staticmethod
    def log_error(
        error_type: str,
        error_message: str,
        endpoint: str,
        details: Dict = None
    ):
        """Log error"""
        log.error(
            "error_occurred",
            error_type=error_type,
            error_message=error_message,
            endpoint=endpoint,
            details=details or {},
            timestamp=datetime.utcnow().isoformat()
        )


class PerformanceMonitor:
    """Performance monitoring"""
    
    # Service metrics
    SERVICE_METRICS = {}
    
    @staticmethod
    def start_timer(service: str) -> float:
        """Start performance timer"""
        return time.time()
    
    @staticmethod
    def end_timer(service: str, start_time: float) -> float:
        """End timer and record latency"""
        elapsed = (time.time() - start_time) * 1000  # Convert to ms
        
        if service not in PerformanceMonitor.SERVICE_METRICS:
            PerformanceMonitor.SERVICE_METRICS[service] = []
        
        PerformanceMonitor.SERVICE_METRICS[service].append(elapsed)
        
        return elapsed
    
    @staticmethod
    def get_service_stats(service: str) -> dict:
        """Get service performance statistics"""
        if service not in PerformanceMonitor.SERVICE_METRICS:
            return {}
        
        values = PerformanceMonitor.SERVICE_METRICS[service][-1000:]  # Last 1000
        
        if not values:
            return {}
        
        sorted_vals = sorted(values)
        count = len(sorted_vals)
        
        return {
            "count": count,
            "min_ms": sorted_vals[0],
            "max_ms": sorted_vals[-1],
            "avg_ms": sum(sorted_vals) / count,
            "p50_ms": sorted_vals[int(count * 0.50)],
            "p95_ms": sorted_vals[int(count * 0.95)],
            "p99_ms": sorted_vals[int(count * 0.99)]
        }
    
    @staticmethod
    def get_all_stats() -> dict:
        """Get all service statistics"""
        return {
            service: PerformanceMonitor.get_service_stats(service)
            for service in PerformanceMonitor.SERVICE_METRICS
        }


class AlertingMetrics:
    """Alert pipeline specific metrics"""
    
    @staticmethod
    def track_alert_pipeline(
        incident_id: str,
        stages: Dict[str, float]  # stage_name: latency_ms
    ):
        """
        Track alert through pipeline
        
        Args:
            incident_id: Incident ID
            stages: Pipeline stages with latencies
        """
        total_latency = sum(stages.values())
        
        log.info(
            "alert_pipeline_complete",
            incident_id=incident_id,
            stages=stages,
            total_latency_ms=total_latency,
            timestamp=datetime.utcnow().isoformat()
        )
    
    @staticmethod
    def track_rca_metrics(
        incident_id: str,
        root_cause_count: int,
        confidence: float,
        latency_ms: float
    ):
        """Track RCA analysis metrics"""
        log.info(
            "rca_analysis_complete",
            incident_id=incident_id,
            root_cause_count=root_cause_count,
            confidence=confidence,
            latency_ms=latency_ms,
            timestamp=datetime.utcnow().isoformat()
        )


# Global metrics instance
metrics = ApplicationMetrics()
