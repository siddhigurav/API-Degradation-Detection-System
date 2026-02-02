"""In-memory, thread-safe alerter store.

Provides minimal API:
    add_alert(alert: dict) -> None
    get_alerts() -> list[dict]
    get_alert(alert_id: str) -> dict | None

Alerts are stored in a dict keyed by `id`. If an incoming alert does
not include an `id`, one is generated. A `created_at` ISO timestamp is
added when storing.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import threading
import uuid

_lock = threading.RLock()
_alerts: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')


def add_alert(alert: Dict[str, Any]) -> None:
    """Add an alert to the in-memory store.

    The function mutates the supplied alert copy and stores it. It is
    safe to call from multiple threads.
    """
    if not isinstance(alert, dict):
        raise TypeError("alert must be a dict")

    with _lock:
        a = dict(alert)  # shallow copy to avoid shared-mutation surprises
        aid = a.get("id") or str(uuid.uuid4())
        a["id"] = aid
        if "created_at" not in a:
            a["created_at"] = _now_iso()
        _alerts[aid] = a


def get_alerts() -> List[Dict[str, Any]]:
    """Return a list of all stored alerts (shallow copies).

    Results are ordered by `created_at` descending (newest first).
    """
    with _lock:
        items = list(_alerts.values())

    def key_fn(it: Dict[str, Any]) -> str:
        return it.get("created_at", "")

    # sort newest first
    items.sort(key=key_fn, reverse=True)
    return [dict(i) for i in items]


def get_alert(alert_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single alert by id, or None if not found."""
    with _lock:
        a = _alerts.get(alert_id)
        return dict(a) if a is not None else None


__all__ = ["add_alert", "get_alerts", "get_alert"]
