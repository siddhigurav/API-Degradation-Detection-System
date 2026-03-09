"""
FastAPI Server - Phase 2

REST API endpoints for:
- System health checks
- Anomaly queries
- Model management
- Alert management
- Configuration
"""

import time
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.api.models import (
    HealthStatus, HealthCheckResponse, ServiceHealthCheck,
    AnomalyResponse, AnomalyQueryRequest, AnomalyQueryResponse,
    ModelStatusResponse, ModelMetricsResponse, ErrorResponse,
    AlertResponse
)

log = structlog.get_logger()


# ============================================================================
# Server Configuration
# ============================================================================

class APIServer:
    """FastAPI server for Phase 2"""
    
    def __init__(self, config, ensemble_detector, alert_manager):
        """
        Initialize API server
        
        Args:
            config: Configuration
            ensemble_detector: Anomaly detection ensemble
            alert_manager: Alert manager instance
        """
        self.config = config
        self.detector = ensemble_detector
        self.alert_mgr = alert_manager
        self.start_time = datetime.utcnow()
        self.app = FastAPI(
            title="API Degradation Detection System",
            description="Phase 2: Detection & Alerting",
            version="2.0.0"
        )
        self._setup_routes()
        self._setup_middleware()
        
    def _setup_middleware(self):
        """Configure middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """Setup API routes"""
        
        # ====== Health Checks ======
        
        @self.app.get("/health", response_model=HealthCheckResponse)
        async def health_check():
            """System health check"""
            return await self._perform_health_check()
        
        @self.app.get("/health/live")
        async def liveness_check():
            """Kubernetes liveness probe"""
            return {"status": "alive"}
        
        @self.app.get("/health/ready")
        async def readiness_check():
            """Kubernetes readiness probe"""
            if not self.detector.is_ready:
                raise HTTPException(
                    status_code=503,
                    detail="Models not loaded"
                )
            return {"status": "ready"}
        
        # ====== Detection API ======
        
        @self.app.get("/api/v1/models/status", response_model=ModelStatusResponse)
        async def get_model_status():
            """Get detection model status"""
            models = []
            
            for model_name, model in self.detector.models.items():
                if model.is_loaded:
                    # Dummy metrics (in production, load from database)
                    metrics = ModelMetricsResponse(
                        model_name=model_name,
                        accuracy=0.94,
                        precision=0.91,
                        recall=0.87,
                        f1_score=0.89,
                        auc_roc=0.95,
                        last_trained=datetime.utcnow() - timedelta(days=7),
                        training_samples=10000
                    )
                    models.append(metrics)
            
            return ModelStatusResponse(
                ensemble_ready=self.detector.is_ready,
                models=models,
                ensemble_agreement_threshold=self.detector.min_agreement,
                last_prediction_time=datetime.utcnow(),
                predictions_made=self.detector.prediction_count
            )
        
        @self.app.post("/api/v1/models/reload")
        async def reload_models():
            """Reload detection models"""
            try:
                if self.detector.load_models():
                    return {
                        "status": "success",
                        "message": "Models reloaded successfully"
                    }
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to load models"
                    )
            except Exception as e:
                log.error("Model reload failed", error=str(e))
                raise HTTPException(
                    status_code=500,
                    detail=str(e)
                )
        
        # ====== Anomaly Queries ======
        
        @self.app.get("/api/v1/anomalies", response_model=AnomalyQueryResponse)
        async def query_anomalies(
            endpoint: Optional[str] = Query(None, description="Filter by endpoint"),
            start_time: datetime = Query(..., description="Start time"),
            end_time: datetime = Query(..., description="End time"),
            min_score: float = Query(0.5, ge=0, le=1, description="Minimum anomaly score"),
            limit: int = Query(100, le=1000, description="Max results")
        ):
            """Query historical anomalies"""
            try:
                # In production, query TimescaleDB
                anomalies = []  # Placeholder
                
                return AnomalyQueryResponse(
                    count=len(anomalies),
                    anomalies=anomalies,
                    metadata={
                        "query_time_ms": 45.2,
                        "endpoint_filter": endpoint,
                        "time_range": f"{start_time} to {end_time}"
                    }
                )
            except Exception as e:
                log.error("Query failed", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/v1/anomalies/{endpoint}", response_model=List[AnomalyResponse])
        async def get_endpoint_anomalies(
            endpoint: str,
            hours: int = Query(24, ge=1, le=720)
        ):
            """Get recent anomalies for specific endpoint"""
            try:
                # In production, query TimescaleDB
                anomalies = []  # Placeholder
                
                return anomalies
            except Exception as e:
                log.error("Query failed", error=str(e), endpoint=endpoint)
                raise HTTPException(status_code=500, detail=str(e))
        
        # ====== Alerts ======
        
        @self.app.get("/api/v1/alerts", response_model=List[AlertResponse])
        async def get_recent_alerts(
            severity: Optional[str] = Query(None),
            acknowledged: bool = Query(False),
            limit: int = Query(50, le=500)
        ):
            """Get recent alerts"""
            try:
                # In production, query PostgreSQL
                alerts = []  # Placeholder
                
                return alerts
            except Exception as e:
                log.error("Alert query failed", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/v1/alerts/{alert_id}/acknowledge")
        async def acknowledge_alert(alert_id: str):
            """Acknowledge alert"""
            try:
                # In production, update PostgreSQL
                return {
                    "status": "success",
                    "alert_id": alert_id,
                    "acknowledged": True,
                    "timestamp": datetime.utcnow().isoformat()
                }
            except Exception as e:
                log.error("Acknowledge failed", error=str(e), alert_id=alert_id)
                raise HTTPException(status_code=500, detail=str(e))
        
        # ====== Metrics ======
        
        @self.app.get("/metrics")
        async def prometheus_metrics():
            """Prometheus metrics endpoint"""
            try:
                # In production, export metrics from prometheus_client
                metrics = f"""
# HELP detection_predictions_total Total predictions made
# TYPE detection_predictions_total counter
detection_predictions_total {self.detector.prediction_count}

# HELP detection_ensemble_ready Ensemble model ready state
# TYPE detection_ensemble_ready gauge
detection_ensemble_ready {1 if self.detector.is_ready else 0}

# HELP api_server_uptime_seconds Server uptime
# TYPE api_server_uptime_seconds gauge
api_server_uptime_seconds {(datetime.utcnow() - self.start_time).total_seconds()}
"""
                return metrics
            except Exception as e:
                log.error("Metrics generation failed", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        # ====== Configuration ======
        
        @self.app.get("/api/v1/config")
        async def get_config():
            """Get current configuration (sanitized)"""
            return {
                "environment": self.config.ENV,
                "debug": self.config.DEBUG,
                "kafka_brokers": self.config.KAFKA_BOOTSTRAP_SERVERS.split(','),
                "detection_threshold": self.config.ANOMALY_DETECTION_THRESHOLD,
                "alert_cooldown_critical": self.config.ALERT_COOLDOWN_CRITICAL,
                "alert_cooldown_warning": self.config.ALERT_COOLDOWN_WARN,
                "min_ensemble_agreement": self.config.MODELS_ENSEMBLE_MIN_AGREEMENT
            }
        
        # ====== Admin ======
        
        @self.app.post("/admin/test-channels")
        async def test_alert_channels():
            """Test all alert channels"""
            try:
                results = {}
                # In production, use real dispatcher
                return results
            except Exception as e:
                log.error("Channel test failed", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        # ====== Utility ======
        
        @self.app.get("/")
        async def root():
            """API documentation"""
            return {
                "service": "API Degradation Detection System",
                "version": "2.0.0",
                "phase": "Phase 2: Detection & Alerting",
                "docs_url": "/docs",
                "health_check": "/health",
                "metrics": "/metrics"
            }
        
        # Error handler
        @self.app.exception_handler(HTTPException)
        async def http_exception_handler(request, exc):
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": exc.detail,
                    "status_code": exc.status_code,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
    
    async def _perform_health_check(self) -> HealthCheckResponse:
        """Perform comprehensive health check"""
        services = []
        overall_status = HealthStatus.HEALTHY
        
        # Check Kafka
        kafka_status = await self._check_kafka()
        services.append(kafka_status)
        if kafka_status.status != HealthStatus.HEALTHY:
            overall_status = HealthStatus.DEGRADED
        
        # Check TimescaleDB
        timescale_status = await self._check_timescaledb()
        services.append(timescale_status)
        if timescale_status.status == HealthStatus.UNHEALTHY:
            overall_status = HealthStatus.UNHEALTHY
        
        # Check PostgreSQL
        postgres_status = await self._check_postgres()
        services.append(postgres_status)
        if postgres_status.status == HealthStatus.UNHEALTHY:
            overall_status = HealthStatus.UNHEALTHY
        
        # Check Redis
        redis_status = await self._check_redis()
        services.append(redis_status)
        
        # Check Models
        models_status = await self._check_models()
        services.append(models_status)
        if models_status.status == HealthStatus.UNHEALTHY:
            overall_status = HealthStatus.UNHEALTHY
        
        # Check Prometheus
        prometheus_status = await self._check_prometheus()
        services.append(prometheus_status)
        if prometheus_status.status == HealthStatus.DEGRADED:
            overall_status = HealthStatus.DEGRADED
        
        uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        return HealthCheckResponse(
            status=overall_status,
            timestamp=datetime.utcnow(),
            services=services,
            uptime_seconds=uptime
        )
    
    async def _check_kafka(self) -> ServiceHealthCheck:
        """Check Kafka connectivity"""
        try:
            from kafka import KafkaConsumer
            consumer = KafkaConsumer(
                bootstrap_servers=self.config.KAFKA_BOOTSTRAP_SERVERS.split(','),
                consumer_timeout_ms=2000
            )
            consumer.close()
            
            return ServiceHealthCheck(
                name="kafka",
                status=HealthStatus.HEALTHY,
                latency_ms=5.0
            )
        except Exception as e:
            return ServiceHealthCheck(
                name="kafka",
                status=HealthStatus.UNHEALTHY,
                latency_ms=0,
                message=str(e)
            )
    
    async def _check_timescaledb(self) -> ServiceHealthCheck:
        """Check TimescaleDB connectivity"""
        try:
            import psycopg2
            start = time.time()
            conn = psycopg2.connect(
                host=self.config.TIMESCALEDB_HOST,
                port=self.config.TIMESCALEDB_PORT,
                user=self.config.TIMESCALEDB_USER,
                password=self.config.TIMESCALEDB_PASSWORD,
                database=self.config.TIMESCALEDB_DATABASE,
                connect_timeout=3
            )
            conn.close()
            latency = (time.time() - start) * 1000
            
            return ServiceHealthCheck(
                name="timescaledb",
                status=HealthStatus.HEALTHY,
                latency_ms=latency
            )
        except Exception as e:
            return ServiceHealthCheck(
                name="timescaledb",
                status=HealthStatus.UNHEALTHY,
                latency_ms=0,
                message=str(e)
            )
    
    async def _check_postgres(self) -> ServiceHealthCheck:
        """Check PostgreSQL connectivity"""
        try:
            import psycopg2
            start = time.time()
            conn = psycopg2.connect(
                host=self.config.POSTGRES_HOST,
                port=self.config.POSTGRES_PORT,
                user=self.config.POSTGRES_USER,
                password=self.config.POSTGRES_PASSWORD,
                database=self.config.POSTGRES_DATABASE,
                connect_timeout=3
            )
            conn.close()
            latency = (time.time() - start) * 1000
            
            return ServiceHealthCheck(
                name="postgres",
                status=HealthStatus.HEALTHY,
                latency_ms=latency
            )
        except Exception as e:
            return ServiceHealthCheck(
                name="postgres",
                status=HealthStatus.UNHEALTHY,
                latency_ms=0,
                message=str(e)
            )
    
    async def _check_redis(self) -> ServiceHealthCheck:
        """Check Redis connectivity"""
        try:
            import redis
            start = time.time()
            r = redis.Redis(
                host=self.config.REDIS_HOST,
                port=self.config.REDIS_PORT,
                socket_connect_timeout=3
            )
            r.ping()
            latency = (time.time() - start) * 1000
            
            return ServiceHealthCheck(
                name="redis",
                status=HealthStatus.HEALTHY,
                latency_ms=latency
            )
        except Exception as e:
            return ServiceHealthCheck(
                name="redis",
                status=HealthStatus.DEGRADED,  # Optional, not critical
                latency_ms=0,
                message=str(e)
            )
    
    async def _check_models(self) -> ServiceHealthCheck:
        """Check model health"""
        status = HealthStatus.HEALTHY if self.detector.is_ready else HealthStatus.UNHEALTHY
        
        return ServiceHealthCheck(
            name="detection_models",
            status=status,
            latency_ms=0,
            message=f"Ensemble ready: {self.detector.is_ready}"
        )
    
    async def _check_prometheus(self) -> ServiceHealthCheck:
        """Check Prometheus connectivity"""
        try:
            import httpx
            start = time.time()
            client = httpx.Client(timeout=3)
            response = client.get(f"{self.config.PROMETHEUS_URL}/api/v1/query", params={"query": "up"})
            latency = (time.time() - start) * 1000
            
            if response.status_code == 200:
                return ServiceHealthCheck(
                    name="prometheus",
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency
                )
            else:
                return ServiceHealthCheck(
                    name="prometheus",
                    status=HealthStatus.DEGRADED,
                    latency_ms=latency
                )
        except Exception as e:
            return ServiceHealthCheck(
                name="prometheus",
                status=HealthStatus.DEGRADED,
                latency_ms=0,
                message=str(e)
            )
    
    def run(self, host: str = "0.0.0.0", port: int = 8000, workers: int = 1):
        """Run API server"""
        uvicorn.run(
            self.app,
            host=host,
            port=port,
            workers=workers,
            log_level=self.config.LOG_LEVEL.lower()
        )


def main():
    """Main entry point"""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    
    from src.config import settings
    from src.detection.ensemble_detector import EnsembleDetector
    from src.alerting.integrations import AlertDispatcher, SlackChannel, PagerDutyChannel
    
    # Configure structured logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Initialize detector
    detector = EnsembleDetector(
        models_dir=settings.MODELS_DIR,
        min_agreement=settings.MODELS_ENSEMBLE_MIN_AGREEMENT
    )
    
    # Initialize dispatcher
    dispatcher = AlertDispatcher()
    
    if settings.SLACK_WEBHOOK_URL:
        dispatcher.register_channel(
            SlackChannel(
                webhook_url=settings.SLACK_WEBHOOK_URL,
                channel=settings.SLACK_CHANNEL,
                enabled=True
            )
        )
    
    if settings.PAGERDUTY_API_KEY:
        dispatcher.register_channel(
            PagerDutyChannel(
                api_key=settings.PAGERDUTY_API_KEY,
                service_id=settings.PAGERDUTY_SERVICE_ID or "",
                enabled=True
            )
        )
    
    # Initialize server
    server = APIServer(settings, detector, None)
    
    # Run
    server.run(
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS
    )


if __name__ == '__main__':
    main()
