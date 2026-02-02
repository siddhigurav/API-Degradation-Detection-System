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

# Alerts storage
ALERTS_DB = Path(os.environ.get('ALERTS_DB', DATA_DIR / 'alerts.db'))
ALERTS_FILE = Path(os.environ.get('ALERTS_FILE', DATA_DIR / 'alerts.jsonl'))

# Server settings
HOST = os.environ.get('HOST', '127.0.0.1')
PORT = int(os.environ.get('PORT', '8001'))

# Logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')


def db_path() -> str:
    """Return string path for alerts DB (for sqlite3)."""
    return str(ALERTS_DB)
