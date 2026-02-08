"""Rolling Metrics Aggregator.

This module implements a RollingMetricsAggregator class that maintains
time-windowed metrics for API endpoints in memory using rolling windows.

Public API:
    RollingMetricsAggregator: Class to aggregate metrics in real-time.

Metrics tracked per window:
    - avg_latency (float, ms)
    - p50_latency (float, ms)
    - p95_latency (float, ms)
    - p99_latency (float, ms)
    - error_rate (float, fraction)
    - request_volume (int)

Supported windows: 60s (1m), 300s (5m), 900s (15m)
"""

from typing import Dict, List, Any, Optional, Deque
from datetime import datetime, timezone
from collections import defaultdict, deque
import math


class RollingMetricsAggregator:
    """Maintains rolling window metrics for API endpoints."""

    WINDOWS = [60, 300, 900]  # seconds

    def __init__(self):
        # endpoint -> window_sec -> deque of (timestamp, latency, status)
        self.data: Dict[str, Dict[int, Deque[tuple]]] = defaultdict(lambda: defaultdict(deque))

    def add_log(self, log: Dict[str, Any]) -> None:
        """Add a log entry to the aggregator."""
        parsed = self._parse_log(log)
        if not parsed:
            return

        endpoint, timestamp, latency, status = parsed
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for window_sec in self.WINDOWS:
            dq = self.data[endpoint][window_sec]
            dq.append((timestamp, latency, status))
            # Clean old entries
            cutoff = now.timestamp() - window_sec
            while dq and dq[0][0].timestamp() < cutoff:
                dq.popleft()

    def get_metrics(self, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """Get current metrics for endpoint(s)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = {}

        endpoints = [endpoint] if endpoint else list(self.data.keys())

        for ep in endpoints:
            if ep not in self.data:
                continue
            result[ep] = {}
            for window_sec in self.WINDOWS:
                dq = self.data[ep][window_sec]
                # Clean before computing
                cutoff = now.timestamp() - window_sec
                while dq and dq[0][0].timestamp() < cutoff:
                    dq.popleft()
                if not dq:
                    continue
                metrics = self._compute_metrics(dq)
                window_name = f"window_{window_sec//60}m"
                result[ep][window_name] = metrics

        return result

    def _parse_log(self, log: Dict[str, Any]) -> Optional[tuple]:
        """Parse log entry."""
        try:
            endpoint = log.get('endpoint')
            if not endpoint or not isinstance(endpoint, str):
                return None

            ts = log.get('timestamp')
            if isinstance(ts, str):
                if ts.endswith('Z'):
                    ts = ts[:-1] + '+00:00'
                timestamp = datetime.fromisoformat(ts)
            elif isinstance(ts, (int, float)):
                timestamp = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
            else:
                return None

            latency = log.get('latency_ms')
            if not isinstance(latency, (int, float)) or latency < 0:
                return None

            status = log.get('status_code')
            if not isinstance(status, int):
                return None

            return endpoint, timestamp, float(latency), status
        except Exception:
            return None

    def _compute_metrics(self, dq: Deque[tuple]) -> Dict[str, Any]:
        """Compute metrics from deque of (timestamp, latency, status)."""
        latencies = [lat for _, lat, _ in dq]
        statuses = [stat for _, _, stat in dq]

        if not latencies:
            return {}

        count = len(latencies)
        avg_latency = sum(latencies) / count

        sorted_lat = sorted(latencies)
        p50 = self._percentile(sorted_lat, 0.50)
        p95 = self._percentile(sorted_lat, 0.95)
        p99 = self._percentile(sorted_lat, 0.99)

        error_count = sum(1 for s in statuses if s >= 400)
        error_rate = error_count / count if count > 0 else 0

        return {
            'avg_latency': round(avg_latency, 2),
            'p50_latency': round(p50, 2),
            'p95_latency': round(p95, 2),
            'p99_latency': round(p99, 2),
            'error_rate': round(error_rate, 4),
            'request_volume': count,
        }

    @staticmethod
    def _percentile(sorted_list: List[float], p: float) -> float:
        """Compute percentile from sorted list."""
        n = len(sorted_list)
        if n == 0:
            return 0
        rank = (n - 1) * p
        lower = int(rank)
        upper = min(lower + 1, n - 1)
        weight = rank - lower
        return sorted_list[lower] * (1 - weight) + sorted_list[upper] * weight


# For backward compatibility
def compute_aggregates(now=None):
    """Compute aggregates using rolling aggregator."""
    import os
    import json
    from datetime import datetime, timezone

    BASE_DIR = os.path.dirname(__file__)
    DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'data'))
    RAW_LOGS = os.path.join(DATA_DIR, 'raw_logs.jsonl')

    now = now or datetime.now(timezone.utc)
    
    agg = RollingMetricsAggregator()
    
    # Load existing logs
    if os.path.exists(RAW_LOGS):
        with open(RAW_LOGS, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    log = json.loads(line)
                    agg.add_log(log)
                except Exception:
                    continue
    
    # Get metrics
    metrics = agg.get_metrics()
    
    # Flatten
    results = []
    for endpoint, windows in metrics.items():
        for window_name, mets in windows.items():
            window_min = int(window_name.split('_')[1][:-1])
            rec = {
                'endpoint': endpoint,
                'window': f'{window_min}m',
                'avg_latency': mets['avg_latency'],
                'p95_latency': mets['p95_latency'],
                'error_rate': mets['error_rate'],
                'request_volume': mets['request_volume'],
                'response_var': 0.0,
                'timestamp': now.isoformat().replace('+00:00', 'Z')
            }
            results.append(rec)
    
    return results


if __name__ == '__main__':
    # Example usage
    agg = RollingMetricsAggregator()

    # Add some logs
    logs = [
        {'endpoint': '/checkout', 'latency_ms': 120, 'status_code': 200, 'timestamp': '2026-02-07T10:00:00Z'},
        {'endpoint': '/checkout', 'latency_ms': 500, 'status_code': 500, 'timestamp': '2026-02-07T10:00:30Z'},
        {'endpoint': '/login', 'latency_ms': 80, 'status_code': 200, 'timestamp': '2026-02-07T10:00:10Z'},
    ]

    for log in logs:
        agg.add_log(log)

    import pprint
    pprint.pprint(agg.get_metrics())

