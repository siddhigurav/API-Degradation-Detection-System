"""Application configuration.

Reads from environment variables with sane defaults suitable for local
development and CI. Keep values simple and explicit.
"""
from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

# Data directory
DATA_DIR = Path(os.environ.get('DATA_DIR', PROJECT_ROOT / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Storage Backend Configuration
# Choose your storage backend: 'memory', 'sqlite', 'redis', 'timescale'
STORAGE_BACKEND = os.environ.get('STORAGE_BACKEND', 'memory')

# SQLite Configuration (default production backend)
SQLITE_DB_PATH = Path(os.environ.get('SQLITE_DB_PATH', DATA_DIR / 'alerts.db'))

# Redis Configuration (high-performance backend)
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
REDIS_KEY_PREFIX = os.environ.get('REDIS_KEY_PREFIX', 'alerts:')

# TimescaleDB Configuration (time-series analytics backend)
TIMESCALE_CONNECTION_STRING = os.environ.get('TIMESCALE_CONNECTION_STRING',
                                           'postgresql://localhost:5432/alerts')

# Server settings
HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', '8001'))

# Logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Alerting Configuration
ALERT_SEVERITY_LEVELS = ['INFO', 'WARN', 'CRITICAL']

# Cool-down periods (seconds) - prevent alert spam
ALERT_COOLDOWN_INFO = int(os.environ.get('ALERT_COOLDOWN_INFO', '3600'))  # 1 hour
ALERT_COOLDOWN_WARN = int(os.environ.get('ALERT_COOLDOWN_WARN', '1800'))  # 30 minutes
ALERT_COOLDOWN_CRITICAL = int(os.environ.get('ALERT_COOLDOWN_CRITICAL', '300'))  # 5 minutes

# Alert Channels
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
EMAIL_SMTP_SERVER = os.environ.get('EMAIL_SMTP_SERVER')
EMAIL_SMTP_PORT = int(os.environ.get('EMAIL_SMTP_PORT', '587'))
EMAIL_USERNAME = os.environ.get('EMAIL_USERNAME')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'alerts@api-monitor.local')
EMAIL_TO = os.environ.get('EMAIL_TO', '').split(',') if os.environ.get('EMAIL_TO') else []

# Alert Routing - which channels for each severity
ALERT_CHANNELS_INFO = os.environ.get('ALERT_CHANNELS_INFO', 'console').split(',')
ALERT_CHANNELS_WARN = os.environ.get('ALERT_CHANNELS_WARN', 'console,slack').split(',')
ALERT_CHANNELS_CRITICAL = os.environ.get('ALERT_CHANNELS_CRITICAL', 'console,slack,email').split(',')

# Deduplication window (seconds) - alerts with same endpoint+severity within this window are deduplicated
ALERT_DEDUP_WINDOW = int(os.environ.get('ALERT_DEDUP_WINDOW', '600'))  # 10 minutes


def db_path() -> str:
    """Return string path for alerts DB (for sqlite3)."""
    return str(ALERTS_DB)
