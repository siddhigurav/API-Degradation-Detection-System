"""
Log Aggregation Module

This module reads ingested API logs from data/raw_logs.jsonl and computes rolling window aggregates
(1m, 5m, 15m) per endpoint. It uses efficient time bucketing via pandas filtering and grouping.

Output: Structured metrics per endpoint-window, suitable for anomaly detection (e.g., avg_latency, p95_latency, etc.).

Storage: Supports both SQLite (recommended for production) and JSONL file persistence.

Example Input (raw_logs.jsonl lines):
{"timestamp": "2026-01-01T10:00:00Z", "endpoint": "/checkout", "status_code": 200, "latency_ms": 120, "response_size": 1024}
{"timestamp": "2026-01-01T10:00:30Z", "endpoint": "/checkout", "status_code": 500, "latency_ms": 500, "response_size": 512}

Example Output (aggregates table / aggregates.jsonl lines):
{"endpoint": "/checkout", "window": "5m", "avg_latency": 420.0, "p95_latency": 610.0, "error_rate": 0.04, "request_volume": 980, "response_var": 32000.0, "timestamp": "2026-01-01T12:05:00Z"}
"""

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
    Compute aggregates for each window per endpoint.
    Uses efficient filtering: only logs within the window are processed.
    Persists to SQLite (recommended) or JSONL file.
    """
    now = now or datetime.now(timezone.utc)
    df = read_raw_logs()
    if df.empty:
        return []
    results = []
    for w in WINDOWS_MIN:
        window_start = pd.Timestamp(now - timedelta(minutes=w))
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
                'window': f'{w}m',
                'avg_latency': avg_latency,
                'p95_latency': p95_latency,
                'error_rate': error_rate,
                'request_volume': request_volume,
                'response_var': resp_size_var,
                'timestamp': now.isoformat().replace('+00:00', 'Z')
            }
            results.append(rec)
    
    # Persist aggregates based on storage mode
    if STORAGE_MODE == 'sqlite':
        persist_aggregates_to_db(results)
    else:
        # Fallback to JSONL persistence
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(AGG_LOGS, 'a', encoding='utf-8') as fh:
            for r in results:
                fh.write(json.dumps(r) + '\n')
    
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
