"""
API Request/Response Models

Pydantic models for FastAPI endpoint validation and documentation.
"""

from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    """Alert severity levels"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class HealthStatus(str, Enum):
    """Service health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


# ============================================================================
# Health Check Models
# ============================================================================

class ServiceHealthCheck(BaseModel):
    """Individual service health status"""
    name: str = Field(..., description="Service name")
    status: HealthStatus = Field(..., description="Health status")
    latency_ms: float = Field(..., description="Response time in milliseconds")
    message: Optional[str] = Field(default=None)
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "kafka",
                "status": "healthy",
                "latency_ms": 12.5,
                "message": None
            }
        }


class HealthCheckResponse(BaseModel):
    """Overall system health status"""
    status: HealthStatus = Field(..., description="Overall system health")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: List[ServiceHealthCheck] = Field(..., description="Per-service health")
    uptime_seconds: float = Field(..., description="Server uptime in seconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2024-01-15T10:30:00Z",
                "services": [
                    {"name": "kafka", "status": "healthy", "latency_ms": 12.5},
                    {"name": "timescaledb", "status": "healthy", "latency_ms": 8.3}
                ],
                "uptime_seconds": 3600.0
            }
        }


# ============================================================================
# Anomaly Detection Models
# ============================================================================

class MetricValue(BaseModel):
    """Single metric measurement"""
    name: str = Field(..., description="Metric name (e.g., 'latency_p99')")
    value: float = Field(..., description="Metric value")
    unit: str = Field(default="ms", description="Unit of measurement")


class AnomalyRequest(BaseModel):
    """Request to detect anomalies"""
    endpoint: str = Field(..., description="API endpoint (e.g., 'GET /users')")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    features: Dict[str, float] = Field(..., description="Feature dictionary from feature-store")
    
    class Config:
        json_schema_extra = {
            "example": {
                "endpoint": "POST /api/v1/orders",
                "timestamp": "2024-01-15T10:30:15Z",
                "features": {
                    "latency_mean": 125.5,
                    "latency_p99": 250.0,
                    "error_rate": 0.02,
                    "cpu_usage": 65.5
                }
            }
        }


class ModelPrediction(BaseModel):
    """Prediction from a single model"""
    model_name: str = Field(..., description="Model name (isolation_forest, lstm, prophet, svm)")
    is_anomaly: bool = Field(..., description="Anomaly detected by this model")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score (0-1)")
    score: float = Field(..., description="Raw anomaly score from model")
    
    class Config:
        json_schema_extra = {
            "example": {
                "model_name": "isolation_forest",
                "is_anomaly": True,
                "confidence": 0.85,
                "score": -0.42
            }
        }


class AnomalyResponse(BaseModel):
    """Response with detected anomalies"""
    endpoint: str = Field(..., description="Monitored endpoint")
    timestamp: datetime = Field(..., description="Detection time")
    is_anomaly: bool = Field(..., description="Ensemble consensus: anomaly detected?")
    anomaly_score: float = Field(..., ge=0, le=1, description="Overall anomaly score (0-1)")
    confidence: float = Field(..., ge=0, le=1, description="Ensemble confidence")
    agreement_count: int = Field(..., ge=0, le=4, description="Number of models agreeing")
    model_predictions: List[ModelPrediction] = Field(..., description="Individual model results")
    feature_summary: Dict[str, float] = Field(..., description="Summary of key features")
    
    class Config:
        json_schema_extra = {
            "example": {
                "endpoint": "POST /api/v1/orders",
                "timestamp": "2024-01-15T10:30:15Z",
                "is_anomaly": True,
                "anomaly_score": 0.78,
                "confidence": 0.92,
                "agreement_count": 3,
                "model_predictions": [
                    {
                        "model_name": "isolation_forest",
                        "is_anomaly": True,
                        "confidence": 0.95,
                        "score": -0.42
                    },
                    {
                        "model_name": "lstm",
                        "is_anomaly": True,
                        "confidence": 0.88,
                        "score": 2.15
                    }
                ],
                "feature_summary": {
                    "latency_mean": 125.5,
                    "error_rate": 0.02
                }
            }
        }


# ============================================================================
# Alert Models
# ============================================================================

class AlertRequest(BaseModel):
    """Request to create alert"""
    endpoint: str = Field(..., description="Affected endpoint")
    severity: SeverityLevel = Field(..., description="Alert severity")
    title: str = Field(..., description="Alert title")
    description: str = Field(..., description="Alert description")
    metrics: Dict[str, float] = Field(..., description="Relevant metrics at time of alert")
    anomaly_score: float = Field(..., ge=0, le=1)
    
    class Config:
        json_schema_extra = {
            "example": {
                "endpoint": "POST /api/v1/orders",
                "severity": "CRITICAL",
                "title": "Latency spike detected",
                "description": "p99 latency increased by 300% over baseline",
                "metrics": {"latency_p99": 750.0, "error_rate": 0.05},
                "anomaly_score": 0.92
            }
        }


class AlertResponse(BaseModel):
    """Response after alert creation"""
    alert_id: str = Field(..., description="Unique alert identifier")
    timestamp: datetime = Field(..., description="Alert creation time")
    endpoint: str = Field(...)
    severity: SeverityLevel = Field(...)
    title: str = Field(...)
    acknowledged: bool = Field(default=False)
    incident_id: Optional[str] = Field(default=None, description="Grouped incident ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "alert_id": "alrt_abc123def456",
                "timestamp": "2024-01-15T10:30:20Z",
                "endpoint": "POST /api/v1/orders",
                "severity": "CRITICAL",
                "title": "Latency spike detected",
                "acknowledged": False,
                "incident_id": "incident_xyz789"
            }
        }


class IncidentResponse(BaseModel):
    """Grouped incident response"""
    incident_id: str = Field(..., description="Unique incident identifier")
    endpoints: List[str] = Field(..., description="Affected endpoints")
    severity: SeverityLevel = Field(..., description="Highest severity among alerts")
    title: str = Field(..., description="Incident title")
    alert_count: int = Field(..., description="Number of grouped alerts")
    first_seen: datetime = Field(..., description="First alert timestamp")
    last_updated: datetime = Field(..., description="Most recent alert timestamp")
    root_cause: Optional[str] = Field(default=None, description="Identified root cause (Phase 3)")
    status: str = Field(default="active", description="incident status (active, resolved, acknowledged)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "incident_id": "incident_xyz789",
                "endpoints": ["POST /api/v1/orders", "POST /api/v1/payments"],
                "severity": "CRITICAL",
                "title": "Payment service degradation",
                "alert_count": 5,
                "first_seen": "2024-01-15T10:30:00Z",
                "last_updated": "2024-01-15T10:45:30Z",
                "root_cause": None,
                "status": "active"
            }
        }


# ============================================================================
# Query Models
# ============================================================================

class AnomalyQueryRequest(BaseModel):
    """Request to query historical anomalies"""
    endpoint: Optional[str] = Field(default=None, description="Filter by endpoint")
    start_time: datetime = Field(..., description="Start time (inclusive)")
    end_time: datetime = Field(..., description="End time (inclusive)")
    min_score: float = Field(default=0.5, ge=0, le=1, description="Minimum anomaly score filter")
    limit: int = Field(default=100, le=1000, description="Max results")


class AnomalyQueryResponse(BaseModel):
    """Response with historical anomalies"""
    count: int = Field(..., description="Number of results")
    anomalies: List[AnomalyResponse] = Field(...)
    metadata: Dict[str, any] = Field(default_factory=dict)
    
    class Config:
        json_schema_extra = {
            "example": {
                "count": 3,
                "anomalies": [],
                "metadata": {"query_time_ms": 125.5}
            }
        }


class ModelMetricsResponse(BaseModel):
    """Model performance metrics"""
    model_name: str = Field(...)
    accuracy: float = Field(..., ge=0, le=1)
    precision: float = Field(..., ge=0, le=1)
    recall: float = Field(..., ge=0, le=1)
    f1_score: float = Field(..., ge=0, le=1)
    auc_roc: float = Field(..., ge=0, le=1)
    last_trained: datetime = Field(...)
    training_samples: int = Field(...)
    
    class Config:
        json_schema_extra = {
            "example": {
                "model_name": "isolation_forest",
                "accuracy": 0.95,
                "precision": 0.92,
                "recall": 0.88,
                "f1_score": 0.90,
                "auc_roc": 0.96,
                "last_trained": "2024-01-10T08:00:00Z",
                "training_samples": 10000
            }
        }


class ModelStatusResponse(BaseModel):
    """Status of all detection models"""
    ensemble_ready: bool = Field(..., description="All models loaded and ready")
    models: List[ModelMetricsResponse] = Field(...)
    ensemble_agreement_threshold: int = Field(..., description="Min models for anomaly consensus")
    last_prediction_time: datetime = Field(...)
    predictions_made: int = Field(..., description="Total predictions since startup")
    
    class Config:
        json_schema_extra = {
            "example": {
                "ensemble_ready": True,
                "models": [],
                "ensemble_agreement_threshold": 2,
                "last_prediction_time": "2024-01-15T10:30:15Z",
                "predictions_made": 15234
            }
        }


# ============================================================================
# Configuration Models
# ============================================================================

class ConfigResponse(BaseModel):
    """Current configuration"""
    environment: str = Field(...)
    debug: bool = Field(...)
    kafka_brokers: List[str] = Field(...)
    detection_threshold: float = Field(...)
    alert_cooldown_critical: int = Field(..., description="Seconds")
    alert_cooldown_warning: int = Field(..., description="Seconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "environment": "production",
                "debug": False,
                "kafka_brokers": ["localhost:9092"],
                "detection_threshold": 0.5,
                "alert_cooldown_critical": 300,
                "alert_cooldown_warning": 1800
            }
        }


class ErrorResponse(BaseModel):
    """Error response"""
    error: str = Field(..., description="Error message")
    status_code: int = Field(..., description="HTTP status code")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Optional[Dict] = Field(default=None)
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Model not loaded",
                "status_code": 503,
                "timestamp": "2024-01-15T10:30:00Z",
                "details": {"model": "lstm", "reason": "File not found"}
            }
        }
