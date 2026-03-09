"""
Production Configuration Manager

Centralizes all configuration from environment variables with sensible defaults.
Supports multiple environments: development, staging, production
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field
import structlog

log = structlog.get_logger()


class Settings(BaseSettings):
    """Production configuration"""
    
    # Environment
    ENV: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    PROJECT_ROOT: Path = BASE_DIR.parent
    DATA_DIR: Path = Field(default=Path(PROJECT_ROOT / 'data'), env="DATA_DIR")
    MODELS_DIR: Path = Field(default=Path(PROJECT_ROOT / 'models'), env="MODELS_DIR")
    
    # Prometheus Configuration
    PROMETHEUS_URL: str = Field(default="http://localhost:9090", env="PROMETHEUS_URL")
    PROMETHEUS_SCRAPE_INTERVAL: int = Field(default=15, env="PROMETHEUS_SCRAPE_INTERVAL")
    PROMETHEUS_REMOTE_WRITE_URL: Optional[str] = Field(default=None, env="PROMETHEUS_REMOTE_WRITE_URL")
    
    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(default="localhost:9092", env="KAFKA_BOOTSTRAP_SERVERS")
    KAFKA_TOPICS: dict = {
        'raw_metrics': 'raw-metrics',
        'features': 'feature-store',
        'anomalies': 'anomalies',
        'alerts': 'alerts',
        'root_causes': 'root-causes'
    }
    KAFKA_CONSUMER_GROUP: str = Field(default="monitoring_service", env="KAFKA_CONSUMER_GROUP")
    KAFKA_AUTO_OFFSET_RESET: str = Field(default="latest", env="KAFKA_AUTO_OFFSET_RESET")
    KAFKA_SESSION_TIMEOUT_MS: int = Field(default=30000, env="KAFKA_SESSION_TIMEOUT_MS")
    
    # TimescaleDB Configuration (Metrics)
    TIMESCALEDB_HOST: str = Field(default="localhost", env="TIMESCALEDB_HOST")
    TIMESCALEDB_PORT: int = Field(default=5432, env="TIMESCALEDB_PORT")
    TIMESCALEDB_USER: str = Field(default="monitoring", env="TIMESCALEDB_USER")
    TIMESCALEDB_PASSWORD: str = Field(default="monitoring_pass_123", env="TIMESCALEDB_PASSWORD")
    TIMESCALEDB_DATABASE: str = Field(default="metrics", env="TIMESCALEDB_DATABASE")
    
    @property
    def TIMESCALEDB_URL(self) -> str:
        return f"postgresql://{self.TIMESCALEDB_USER}:{self.TIMESCALEDB_PASSWORD}@{self.TIMESCALEDB_HOST}:{self.TIMESCALEDB_PORT}/{self.TIMESCALEDB_DATABASE}"
    
    # PostgreSQL Configuration (Alerts, Incidents)
    POSTGRES_HOST: str = Field(default="localhost", env="POSTGRES_HOST")
    POSTGRES_PORT: int = Field(default=5433, env="POSTGRES_PORT")
    POSTGRES_USER: str = Field(default="monitoring", env="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(default="monitoring_pass_123", env="POSTGRES_PASSWORD")
    POSTGRES_DATABASE: str = Field(default="alerts", env="POSTGRES_DATABASE")
    
    @property
    def POSTGRES_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DATABASE}"
    
    @property
    def POSTGRES_ASYNC_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DATABASE}"
    
    # Redis Configuration (Caching)
    REDIS_HOST: str = Field(default="localhost", env="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, env="REDIS_PORT")
    REDIS_PASSWORD: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    REDIS_DB: int = Field(default=0, env="REDIS_DB")
    
    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        else:
            return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # ML Model Configuration
    MODELS_ISOLATION_FOREST_CONTAMINATION: float = Field(default=0.05, env="MODELS_IF_CONTAMINATION")
    MODELS_LSTM_INPUT_DIM: int = Field(default=8, env="MODELS_LSTM_INPUT_DIM")
    MODELS_LSTM_LATENT_DIM: int = Field(default=4, env="MODELS_LSTM_LATENT_DIM")
    MODELS_LSTM_SEQUENCE_LENGTH: int = Field(default=10, env="MODELS_LSTM_SEQUENCE_LENGTH")
    MODELS_ENSEMBLE_MIN_AGREEMENT: int = Field(default=2, env="MODELS_ENSEMBLE_MIN_AGREEMENT")
    ANOMALY_DETECTION_THRESHOLD: float = Field(default=0.5, env="ANOMALY_DETECTION_THRESHOLD")
    
    # Feature Engineering
    FEATURE_WINDOWS: list = [60, 300, 900, 3600]
    FEATURE_BASELINE_UPDATE_ALPHA: float = Field(default=0.1, env="FEATURE_BASELINE_ALPHA")
    FEATURE_Z_SCORE_THRESHOLD: float = Field(default=2.0, env="FEATURE_Z_SCORE_THRESHOLD")
    
    # Alert Configuration
    ALERT_DEDUP_WINDOW_SECONDS: int = Field(default=600, env="ALERT_DEDUP_WINDOW")
    ALERT_COOLDOWN_INFO: int = Field(default=3600, env="ALERT_COOLDOWN_INFO")
    ALERT_COOLDOWN_WARN: int = Field(default=1800, env="ALERT_COOLDOWN_WARN")
    ALERT_COOLDOWN_CRITICAL: int = Field(default=300, env="ALERT_COOLDOWN_CRITICAL")
    MIN_CONSECUTIVE_ANOMALIES: int = Field(default=3, env="MIN_CONSECUTIVE_ANOMALIES")
    
    # Slack Integration
    SLACK_WEBHOOK_URL: Optional[str] = Field(default=None, env="SLACK_WEBHOOK_URL")
    SLACK_CHANNEL: str = Field(default="#alerts", env="SLACK_CHANNEL")
    
    # PagerDuty Integration
    PAGERDUTY_API_KEY: Optional[str] = Field(default=None, env="PAGERDUTY_API_KEY")
    PAGERDUTY_SERVICE_ID: Optional[str] = Field(default=None, env="PAGERDUTY_SERVICE_ID")
    
    # Server Configuration
    HOST: str = Field(default="127.0.0.1", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    WORKERS: int = Field(default=4, env="WORKERS")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Storage Configuration
    STORAGE_BACKEND: str = Field(default="memory", env="STORAGE_BACKEND")
    METRICS_RETENTION_DAYS: int = Field(default=365, env="METRICS_RETENTION_DAYS")
    ALERTS_RETENTION_DAYS: int = Field(default=90, env="ALERTS_RETENTION_DAYS")
    MAX_METRIC_CARDINALITY: int = Field(default=100000, env="MAX_METRIC_CARDINALITY")
    
    # RCA Configuration
    RCA_CONFIDENCE_THRESHOLD: float = Field(default=0.5, env="RCA_CONFIDENCE_THRESHOLD")
    RCA_ENABLE_CAUSAL_INFERENCE: bool = Field(default=True, env="RCA_ENABLE_CAUSAL_INFERENCE")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    def __init__(self, **data):
        super().__init__(**data)


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get global settings instance"""
    return settings


# Module-level constants for backwards compatibility
STORAGE_BACKEND = settings.STORAGE_BACKEND
LOG_LEVEL = settings.LOG_LEVEL
HOST = settings.HOST
PORT = settings.PORT
WORKERS = settings.WORKERS

# Path-based constants
db_path = settings.DATA_DIR / 'alerts.db'
SQLITE_DB_PATH = db_path
ALERTS_FILE = settings.DATA_DIR / 'alerts.jsonl'

# Redis configuration
REDIS_URL = settings.REDIS_URL
REDIS_KEY_PREFIX = 'alerts:'

# TimescaleDB configuration
TIMESCALE_CONNECTION_STRING = settings.TIMESCALEDB_URL
