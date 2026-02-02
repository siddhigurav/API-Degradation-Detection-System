"""Aggregator module.

This module implements a pure function `aggregate_logs` that converts a list
of raw API log records into time-windowed aggregated metrics. It uses only
the Python standard library and contains no I/O side effects.

Public API:
    aggregate_logs(logs: list[dict], window_seconds: int) -> dict

Return format:
    {
        endpoint1: {
            window_start_iso: {metrics...},
            ...
        },
        endpoint2: { ... }
    }

Metrics returned per window:
    - avg_latency (float, ms)
    - p95_latency (float, ms)
    - error_rate (float, fraction)
    - request_count (int)

Supported windows: 60 (1m), 300 (5m)
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from collections import defaultdict
import math


def _parse_timestamp(ts: Any) -> Optional[datetime]:
    """Parse timestamp from ISO string or numeric epoch to naive UTC datetime.

    Returns None on parse failure.
    """
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts), tz=timezone.utc).replace(tzinfo=None)
        if isinstance(ts, str):
            s = ts.strip()
            # Accept Z suffix
            if s.endswith('Z'):
                s = s[:-1] + '+00:00'
            # Use fromisoformat which supports offset
            dt = datetime.fromisoformat(s)
            # normalize to naive UTC
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
    except Exception:
        return None


def _safe_get_number(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        # attempt to parse numeric string
        return float(str(v).strip())
    except Exception:
        return None


def aggregate_logs(logs: List[Dict[str, Any]], window_seconds: int) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Aggregate raw API logs into metrics per endpoint and time window.

    Args:
        logs: list of dicts with fields: endpoint (str), latency_ms (number),
              status_code (int), timestamp (ISO string or epoch)
        window_seconds: window size in seconds (supported: 60, 300)

    Returns:
        Nested dict mapping endpoint -> window_start_iso -> metrics dict.

    Notes:
        - Malformed records are skipped.
        - Pure function: no I/O performed.
    """
    if window_seconds not in (60, 300):
        raise ValueError('Unsupported window_seconds; supported: 60, 300')

    groups: Dict[str, Dict[int, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for rec in logs:
        try:
            endpoint = rec.get('endpoint')
            if not endpoint or not isinstance(endpoint, str):
                continue

            ts = _parse_timestamp(rec.get('timestamp'))
            if ts is None:
                continue

            latency = _safe_get_number(rec.get('latency_ms'))
            if latency is None or latency < 0:
                continue

            status = rec.get('status_code')
            try:
                status = int(status)
            except Exception:
                continue

            epoch = int(ts.timestamp())
            bucket_start = (epoch // window_seconds) * window_seconds

            groups[endpoint][bucket_start].append({'latency': latency, 'status': status})
        except Exception:
            # Defensive: skip any unexpected record
            continue

    result: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for endpoint, buckets in groups.items():
        result[endpoint] = {}
        for bucket_start, items in buckets.items():
            latencies = [it['latency'] for it in items]
            count = len(latencies)
            if count == 0:
                continue
            avg_latency = sum(latencies) / count

            # p95 calculation: nearest-rank method
            sorted_lat = sorted(latencies)
            rank = math.ceil(0.95 * count)
            p95_latency = sorted_lat[max(0, min(rank - 1, count - 1))]

            error_count = sum(1 for it in items if int(it['status']) >= 400)
            error_rate = error_count / count

            window_iso = datetime.fromtimestamp(bucket_start, tz=timezone.utc).replace(tzinfo=None).isoformat() + 'Z'

            result[endpoint][window_iso] = {
                'avg_latency': round(avg_latency, 2),
                'p95_latency': round(float(p95_latency), 2),
                'error_rate': round(error_rate, 4),
                'request_count': count,
                'window_start': window_iso,
                'window_seconds': window_seconds,
            }

    return result


if __name__ == '__main__':
    # Example usage
    sample_logs = [
        {'endpoint': '/checkout', 'latency_ms': 120, 'status_code': 200, 'timestamp': '2026-02-02T15:00:05Z'},
        {'endpoint': '/checkout', 'latency_ms': 500, 'status_code': 500, 'timestamp': '2026-02-02T15:00:30Z'},
        {'endpoint': '/checkout', 'latency_ms': 110, 'status_code': 200, 'timestamp': '2026-02-02T15:01:00Z'},
        {'endpoint': '/login', 'latency_ms': 80, 'status_code': 200, 'timestamp': '2026-02-02T15:00:10Z'},
    ]

    print('Aggregate (1m):')
    out1 = aggregate_logs(sample_logs, 60)
    from pprint import pprint

    pprint(out1)

    print('\nAggregate (5m):')
    pprint(aggregate_logs(sample_logs, 300))

