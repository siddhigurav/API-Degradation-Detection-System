"""
Log Aggregation Module

Pure function that aggregates raw API logs into metrics per endpoint and time window.
No external dependencies or file I/O - pure computational logic.

Design Decisions:
- Pure function: takes raw logs as input, returns aggregated metrics as output
- Time windows: 1m, 5m, 15m rolling windows from current time
- Metrics: avg_latency, p95_latency, error_rate, request_volume, response_size_variance
- Window calculation: Groups logs by endpoint and time bucket, computes statistics
- Error handling: Skips malformed logs, returns empty dict for no data
"""

import math
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict


def aggregate_logs(raw_logs: List[Dict[str, Any]], current_time: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Aggregate raw API logs into metrics per endpoint and time window.

    Args:
        raw_logs: List of raw log entries with timestamp, endpoint, status_code, latency_ms, response_size
        current_time: Reference time for window calculation (defaults to now)

    Returns:
        Dict with aggregated metrics: {(endpoint, window): metrics_dict}
        Where window is "1m", "5m", or "15m"
    """
    if not raw_logs:
        return {}

    if current_time is None:
        current_time = datetime.utcnow()

    # Parse and validate logs
    parsed_logs = []
    for log in raw_logs:
        parsed = _parse_log_entry(log)
        if parsed:
            parsed_logs.append(parsed)

    if not parsed_logs:
        return {}

    # Group logs by endpoint and time window
    windowed_logs = _group_by_windows(parsed_logs, current_time)

    # Compute metrics for each endpoint-window combination
    aggregated = {}
    for (endpoint, window), logs in windowed_logs.items():
        key = f"{endpoint}:{window}"
        aggregated[key] = _compute_metrics(logs)

    return aggregated


def _parse_log_entry(log: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse and validate a single log entry."""
    try:
        # Extract required fields
        timestamp_str = log.get('timestamp')
        if not timestamp_str:
            return None

        # Parse timestamp (handle both ISO and Unix timestamp formats)
        if isinstance(timestamp_str, str):
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str[:-1] + '+00:00'
            timestamp = datetime.fromisoformat(timestamp_str)
        elif isinstance(timestamp_str, (int, float)):
            timestamp = datetime.utcfromtimestamp(timestamp_str)
        else:
            return None

        endpoint = log.get('endpoint')
        if not endpoint or not isinstance(endpoint, str):
            return None

        status_code = log.get('status_code')
        if not isinstance(status_code, int):
            return None

        latency_ms = log.get('latency_ms')
        if not isinstance(latency_ms, (int, float)) or latency_ms < 0:
            return None

        response_size = log.get('response_size', 0)
        if not isinstance(response_size, (int, float)):
            response_size = 0

        return {
            'timestamp': timestamp,
            'endpoint': endpoint,
            'status_code': status_code,
            'latency_ms': float(latency_ms),
            'response_size': float(response_size),
            'is_error': status_code >= 400
        }

    except (ValueError, TypeError):
        return None


def _group_by_windows(logs: List[Dict[str, Any]], current_time: datetime) -> Dict[tuple, List[Dict[str, Any]]]:
    """Group logs by endpoint and time window."""
    windowed = defaultdict(list)
    windows = [1, 5, 15]  # minutes

    for log in logs:
        timestamp = log['timestamp']
        endpoint = log['endpoint']

        for window_minutes in windows:
            # Calculate which window this log belongs to
            window_start = _get_window_start(timestamp, window_minutes, current_time)
            if window_start:
                key = (endpoint, f"{window_minutes}m")
                windowed[key].append(log)

    return dict(windowed)


def _get_window_start(timestamp: datetime, window_minutes: int, current_time: datetime) -> Optional[datetime]:
    """Calculate the start time of the window this timestamp belongs to."""
    # Only include logs within the last window duration from current_time
    time_diff = (current_time - timestamp).total_seconds() / 60  # minutes

    if time_diff < 0 or time_diff >= window_minutes:
        return None

    # Calculate window start (align to window boundaries)
    minutes_since_epoch = int(timestamp.timestamp() / 60)
    window_start_minutes = (minutes_since_epoch // window_minutes) * window_minutes
    window_start = datetime.utcfromtimestamp(window_start_minutes * 60)

    return window_start


def _compute_metrics(logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute all required metrics for a group of logs."""
    if not logs:
        return {}

    latencies = [log['latency_ms'] for log in logs]
    response_sizes = [log['response_size'] for log in logs]
    error_count = sum(1 for log in logs if log['is_error'])

    # Basic statistics
    avg_latency = sum(latencies) / len(latencies)

    # P95 latency (95th percentile)
    sorted_latencies = sorted(latencies)
    p95_index = int(len(sorted_latencies) * 0.95)
    p95_latency = sorted_latencies[min(p95_index, len(sorted_latencies) - 1)]

    # Error rate
    error_rate = error_count / len(logs)

    # Request volume
    request_volume = len(logs)

    # Response size variance
    if len(response_sizes) > 1:
        mean_size = sum(response_sizes) / len(response_sizes)
        response_size_variance = sum((x - mean_size) ** 2 for x in response_sizes) / len(response_sizes)
    else:
        response_size_variance = 0.0

    # Window timestamp (use the latest log timestamp)
    window_timestamp = max(log['timestamp'] for log in logs)

    return {
        'endpoint': logs[0]['endpoint'],
        'window': f"{_infer_window_minutes(logs)}m",
        'avg_latency': round(avg_latency, 2),
        'p95_latency': round(p95_latency, 2),
        'error_rate': round(error_rate, 4),
        'request_volume': request_volume,
        'response_size_variance': round(response_size_variance, 2),
        'timestamp': window_timestamp.isoformat() + 'Z',
        'sample_count': len(logs)
    }


def _infer_window_minutes(logs: List[Dict[str, Any]]) -> int:
    """Infer the window size from log timestamps."""
    if len(logs) < 2:
        return 1  # Default to 1m for single logs

    timestamps = sorted(log['timestamp'] for log in logs)
    time_span_minutes = (timestamps[-1] - timestamps[0]).total_seconds() / 60

    # Return the smallest window that could contain all logs
    if time_span_minutes <= 1:
        return 1
    elif time_span_minutes <= 5:
        return 5
    else:
        return 15


# Demonstration snippet
if __name__ == "__main__":
    # Sample raw logs
    sample_logs = [
        {
            "timestamp": "2024-01-01T10:00:00Z",
            "endpoint": "/checkout",
            "status_code": 200,
            "latency_ms": 120,
            "response_size": 1024
        },
        {
            "timestamp": "2024-01-01T10:00:30Z",
            "endpoint": "/checkout",
            "status_code": 500,
            "latency_ms": 500,
            "response_size": 512
        },
        {
            "timestamp": "2024-01-01T10:01:00Z",
            "endpoint": "/checkout",
            "status_code": 200,
            "latency_ms": 110,
            "response_size": 1080
        }
    ]

    current_time = datetime(2024, 1, 1, 10, 2, 0)  # 2 minutes after first log

    print("🔄 Log Aggregation Demo")
    print("=" * 40)

    aggregated = aggregate_logs(sample_logs, current_time)

    print(f"📊 Generated {len(aggregated)} aggregated metrics:")
    print()

    for key, metrics in aggregated.items():
        print(f"🔸 {key}:")
        print(f"   Avg Latency: {metrics['avg_latency']}ms")
        print(f"   P95 Latency: {metrics['p95_latency']}ms")
        print(f"   Error Rate: {metrics['error_rate']:.1%}")
        print(f"   Request Volume: {metrics['request_volume']}")
        print(f"   Response Size Variance: {metrics['response_size_variance']}")
        print()

    print("✅ Aggregation complete!")

import os
import json
import sqlite3
from datetime import datetime, timedelta, timezone
import pandas as pd

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'data'))
RAW_LOGS = os.path.join(DATA_DIR, 'raw_logs.jsonl')
AGG_LOGS = os.path.join(DATA_DIR, 'aggregates.jsonl')
AGG_DB = os.path.join(DATA_DIR, 'aggregates.db')

# Storage mode: 'sqlite' or 'jsonl'
STORAGE_MODE = os.getenv('AGG_STORAGE_MODE', 'sqlite')

WINDOWS_MIN = [1, 5, 15]


def read_raw_logs():
    if not os.path.exists(RAW_LOGS):
        return pd.DataFrame()
    records = []
    with open(RAW_LOGS, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True)
    return df


def init_aggregates_db():
    """Initialize SQLite database for aggregates if using SQLite storage."""
    if STORAGE_MODE != 'sqlite':
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(AGG_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS aggregates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL,
            window_minutes INTEGER NOT NULL,
            window_end TEXT NOT NULL,
            avg_latency REAL NOT NULL,
            p95_latency REAL NOT NULL,
            error_rate REAL NOT NULL,
            request_volume INTEGER NOT NULL,
            response_size_variance REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(endpoint, window_minutes, window_end)
        )
    ''')
    conn.commit()
    conn.close()


def read_aggregates_from_db():
    """Read all aggregates from SQLite database."""
    if STORAGE_MODE != 'sqlite':
        return pd.DataFrame()
    if not os.path.exists(AGG_DB):
        return pd.DataFrame()
    conn = sqlite3.connect(AGG_DB)
    df = pd.read_sql_query("SELECT * FROM aggregates ORDER BY window_end DESC", conn)
    conn.close()
    return df


def persist_aggregates_to_db(aggregates):
    """Persist aggregates to SQLite database."""
    if STORAGE_MODE != 'sqlite' or not aggregates:
        return
    init_aggregates_db()
    conn = sqlite3.connect(AGG_DB)
    cursor = conn.cursor()
    for agg in aggregates:
        # Convert window format (e.g., "5m") to minutes
        window_minutes = int(agg['window'].rstrip('m'))
        cursor.execute('''
            INSERT OR REPLACE INTO aggregates 
            (endpoint, window_minutes, window_end, avg_latency, p95_latency, error_rate, request_volume, response_size_variance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            agg['endpoint'],
            window_minutes,
            agg['timestamp'],
            agg['avg_latency'],
            agg['p95_latency'],
            agg['error_rate'],
            agg['request_volume'],
            agg['response_var']
        ))
    conn.commit()
    conn.close()


def read_aggregates():
    """Read aggregates from appropriate storage backend."""
    if STORAGE_MODE == 'sqlite':
        df = read_aggregates_from_db()
        if df.empty:
            return pd.DataFrame()
        # Convert window_minutes to window format and rename columns to match expected format
        df['window'] = df['window_minutes'].astype(str) + 'm'
        df = df.rename(columns={
            'window_end': 'timestamp',
            'response_size_variance': 'response_var'
        })
        return df[['endpoint', 'window', 'avg_latency', 'p95_latency', 'error_rate', 'request_volume', 'response_var', 'timestamp']]
    else:
        # Fallback to JSONL
        if not os.path.exists(AGG_LOGS):
            return pd.DataFrame()
        records = []
        with open(AGG_LOGS, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)


def compute_aggregates(now=None):
    """
    Compute aggregates using the rolling aggregator.
    Loads all raw logs into the aggregator and gets current metrics.
    """
    from aggregator import RollingMetricsAggregator

    now = now or datetime.now(timezone.utc)
    df = read_raw_logs()
    if df.empty:
        return []

    # Create aggregator and load all logs
    agg = RollingMetricsAggregator()
    for _, row in df.iterrows():
        log = {
            'endpoint': row['endpoint'],
            'latency_ms': row['latency_ms'],
            'status_code': row['status_code'],
            'timestamp': row['timestamp'].isoformat().replace('+00:00', 'Z')
        }
        agg.add_log(log)

    # Get metrics
    metrics = agg.get_metrics()

    # Flatten to list format
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
                'response_var': 0.0,  # Not computed
                'timestamp': now.isoformat().replace('+00:00', 'Z')
            }
            results.append(rec)
    
    return results


if __name__ == '__main__':
    print(f'Using storage mode: {STORAGE_MODE}')
    if STORAGE_MODE == 'sqlite':
        init_aggregates_db()
        print('Initialized SQLite database for aggregates')
    
    print('Computing aggregates...')
    res = compute_aggregates()
    print(f'Computed {len(res)} aggregate records')
    
    if res:
        print('Sample aggregate:')
        print(json.dumps(res[0], indent=2))
        
        print('\nReading back aggregates...')
        df_agg = read_aggregates()
        print(f'Read {len(df_agg)} aggregate records from storage')
