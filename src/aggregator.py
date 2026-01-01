"""
Log Aggregation Module

This module reads ingested API logs from data/raw_logs.jsonl and computes rolling window aggregates
(1m, 5m, 15m) per endpoint. It uses efficient time bucketing via pandas filtering and grouping.

Output: Structured metrics per endpoint-window, suitable for anomaly detection (e.g., avg_latency, p95_latency, etc.).

Example Input (raw_logs.jsonl lines):
{"timestamp": "2026-01-01T10:00:00Z", "endpoint": "/checkout", "status_code": 200, "latency_ms": 120, "response_size": 1024}
{"timestamp": "2026-01-01T10:00:30Z", "endpoint": "/checkout", "status_code": 500, "latency_ms": 500, "response_size": 512}

Example Output (aggregates.jsonl lines):
{"endpoint": "/checkout", "window_minutes": 1, "window_end": "2026-01-01T10:01:00Z", "avg_latency": 310.0, "p95_latency": 500.0, "error_rate": 0.5, "request_volume": 2, "response_size_variance": 0.0}
"""

import os
import json
from datetime import datetime, timedelta
import pandas as pd

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'data'))
RAW_LOGS = os.path.join(DATA_DIR, 'raw_logs.jsonl')
AGG_LOGS = os.path.join(DATA_DIR, 'aggregates.jsonl')

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
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    return df


def compute_aggregates(now=None):
    """
    Compute aggregates for each window per endpoint.
    Uses efficient filtering: only logs within the window are processed.
    """
    now = now or datetime.utcnow()
    df = read_raw_logs()
    if df.empty:
        return []
    results = []
    for w in WINDOWS_MIN:
        window_start = pd.Timestamp(now - timedelta(minutes=w), tz='UTC')
        df_w = df[df['timestamp'] >= window_start]
        if df_w.empty:
            continue
        grouped = df_w.groupby('endpoint')
        for endpoint, g in grouped:
            avg_latency = float(g['latency_ms'].mean())
            p95_latency = float(g['latency_ms'].quantile(0.95))
            error_rate = float((g['status_code'] >= 500).sum() / len(g))
            request_volume = int(len(g))
            resp_size_var = float(g['response_size'].var(ddof=0) if len(g) > 1 else 0.0)
            rec = {
                'endpoint': endpoint,
                'window_minutes': w,
                'window_end': now.isoformat() + 'Z',
                'avg_latency': avg_latency,
                'p95_latency': p95_latency,
                'error_rate': error_rate,
                'request_volume': request_volume,
                'response_size_variance': resp_size_var,
            }
            results.append(rec)
    # persist aggregates (append)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(AGG_LOGS, 'a', encoding='utf-8') as fh:
        for r in results:
            fh.write(json.dumps(r) + '\n')
    return results


if __name__ == '__main__':
    print('Computing aggregates...')
    res = compute_aggregates()
    print(f'wrote {len(res)} aggregate records')
