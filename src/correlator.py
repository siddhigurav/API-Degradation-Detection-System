"""Correlator module.

Deterministically correlate metric-level anomalies into alert candidates.

Public API:
    correlate(anomalies: list[dict]) -> list[dict]

Input anomaly fields expected (minimum):
    - endpoint (str)
    - window_start (ISO str, e.g. "2026-02-02T15:00:00Z")
    - metric_name (str)
    - severity ("LOW"|"MEDIUM"|"HIGH")

If two or more anomalies share the same endpoint and window_start, a
single alert candidate is emitted containing the combined signals. The
alert `severity` is the maximum severity among its signals.
"""

from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
_RANK_TO_SEVERITY = {v: k for k, v in _SEVERITY_RANK.items()}


def _parse_iso_z(s: str) -> datetime:
    if s.endswith("Z"):
        s2 = s[:-1] + "+00:00"
    else:
        s2 = s
    return datetime.fromisoformat(s2).astimezone(timezone.utc)


def _iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None).isoformat() + "Z"


def correlate(anomalies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group anomalies by endpoint+window_start and emit alert candidates.

    Returned alert dict keys:
        - endpoint
        - severity
        - signals (list of anomalies)
        - window_start
        - window_end
    """
    if not anomalies:
        return []

    groups: Dict[tuple, List[Dict[str, Any]]] = {}

    for a in anomalies:
        endpoint = a.get("endpoint")
        window = a.get("window_start")
        if not endpoint or not window:
            logger.debug("Skipping malformed anomaly: %s", a)
            continue
        key = (endpoint, window)
        groups.setdefault(key, []).append(a)

    alerts: List[Dict[str, Any]] = []
    for (endpoint, window_start) in sorted(groups.keys(), key=lambda t: (t[0], t[1])):
        signals = groups[(endpoint, window_start)]
        if len(signals) < 2:
            continue

        max_rank = max(_SEVERITY_RANK.get(s.get("severity", "LOW"), 1) for s in signals)
        severity = _RANK_TO_SEVERITY.get(max_rank, "LOW")

        # Window duration can be provided per-signal via 'window_seconds'
        window_seconds = None
        for s in signals:
            if isinstance(s.get("window_seconds"), int):
                window_seconds = s["window_seconds"]
                break
        if window_seconds is None:
            window_seconds = 60

        try:
            start_dt = _parse_iso_z(window_start)
            end_dt = start_dt + timedelta(seconds=window_seconds)
            window_end = _iso_z(end_dt)
        except Exception:
            logger.debug("Failed to parse window_start %s", window_start)
            window_end = ""

        norm_signals = sorted(signals, key=lambda s: (s.get("metric_name", ""), str(s.get("deviation_ratio", ""))))

        alert = {
            "endpoint": endpoint,
            "severity": severity,
            "signals": norm_signals,
            "window_start": window_start,
            "window_end": window_end,
        }
        alerts.append(alert)

    return alerts


if __name__ == "__main__":
    sample = [
        {"endpoint": "/a", "window_start": "2026-02-02T15:00:00Z", "metric_name": "avg_latency", "severity": "HIGH"},
        {"endpoint": "/a", "window_start": "2026-02-02T15:00:00Z", "metric_name": "error_rate", "severity": "MEDIUM"},
        {"endpoint": "/b", "window_start": "2026-02-02T15:01:00Z", "metric_name": "avg_latency", "severity": "LOW"},
    ]

    from pprint import pprint
    pprint(correlate(sample))
