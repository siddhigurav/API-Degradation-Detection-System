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
