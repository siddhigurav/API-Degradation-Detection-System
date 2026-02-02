"""Logging helpers for the application.

Provides a small structured logger configuration using standard library
only. Logs are emitted as compact JSON-like records for easier parsing
in production systems.
"""
import logging
import json
from datetime import datetime


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            'ts': datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
            'level': record.levelname,
            'name': record.name,
            'msg': record.getMessage()
        }
        # include extra fields if provided
        if hasattr(record, 'extra') and isinstance(record.extra, dict):
            payload.update(record.extra)
        if record.exc_info:
            payload['exc'] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = 'INFO') -> None:
    """Configure root logger with JSON formatter at given log level.

    Args:
        level: logging level name (INFO, DEBUG, etc.)
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # If handlers already exist (e.g., in tests), avoid adding duplicates
    if any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        for h in root.handlers:
            h.setFormatter(JsonLogFormatter())
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root.addHandler(handler)
