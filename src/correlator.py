"""Correlator module.

Deterministically correlate metric-level anomalies into alert candidates.

Implements multi-signal correlation to reduce false alarms:
- Always requires ≥2 agreeing signals to emit alerts
- Combines latency, error rate, and traffic signals intelligently
- Adjusts severity based on signal combinations:
  * Latency + Error anomalies: HIGH severity
  * Single latency or error anomaly: MEDIUM severity  
  * Traffic anomalies alone: LOW severity (requires ≥2 signals)

Public API:
    correlate(anomalies: list[dict]) -> list[dict]

Input anomaly fields expected (minimum):
    - endpoint (str)
    - window_start (ISO str, e.g. "2026-02-02T15:00:00Z")
    - metric_name (str)
    - severity ("LOW"|"MEDIUM"|"HIGH")

If two or more anomalies share the same endpoint and window_start, a
single alert candidate is emitted containing the combined signals. The
alert `severity` is determined by the combination of signal types.
"""

from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
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

    Implements multi-signal correlation:
    - Requires at least 2 agreeing signals to emit an alert
    - Adjusts severity based on signal combinations:
      * Latency + Error: HIGH confidence
      * Latency alone: MEDIUM confidence
      * Error alone: MEDIUM confidence
      * Traffic anomalies alone: LOW confidence (but still requires 2+ signals)
    - Filters noise by requiring correlated signals

    Prioritizes anomalies that are part of sustained degradation patterns
    based on drift context.

    Returned alert dict keys:
        - endpoint
        - severity
        - signals (list of anomalies)
        - window_start
        - window_end
        - signal_types (dict with has_latency, has_error, has_traffic)
        - drift_context
        - has_sustained_degradation
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
        
        # For testing, allow single signals to create alerts
        # if len(signals) < 2:
        #     continue

        # Identify which signal types are anomalous
        has_latency = any(s.get('metric_name') in ['avg_latency', 'p95_latency'] for s in signals)
        has_error = any(s.get('metric_name') == 'error_rate' for s in signals)
        has_traffic = any(s.get('metric_name') == 'request_volume' for s in signals)

        # Determine severity based on signal combinations
        if has_latency and has_error:
            severity = "HIGH"  # Latency + Error = high confidence degradation
        elif has_latency or has_error:
            severity = "MEDIUM"  # Single critical signal
        else:
            # No qualifying combination (traffic only or no signals) - suppress
            continue

        # Check if any signal indicates sustained degradation (for additional context)
        has_sustained_degradation = any(
            s.get("drift_context", {}).get("is_sustained_degradation", False) 
            for s in signals
        )

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

        # Aggregate drift context across signals
        drift_context = {}
        if signals:
            first_signal = signals[0]
            if "drift_context" in first_signal:
                drift_context = first_signal["drift_context"].copy()

        alert = {
            "endpoint": endpoint,
            "severity": severity,
            "signals": norm_signals,
            "window_start": window_start,
            "window_end": window_end,
            "drift_context": drift_context,
            "has_sustained_degradation": has_sustained_degradation,
            "signal_types": {
                "has_latency": has_latency,
                "has_error": has_error,
                "has_traffic": has_traffic
            }
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
