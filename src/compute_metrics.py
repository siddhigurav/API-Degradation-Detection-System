import json
import os
from datetime import datetime

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
MARKER = os.path.join(DATA_DIR, 'demo_marker.json')
ALERTS = os.path.join(DATA_DIR, 'alerts.jsonl')
RAW = os.path.join(DATA_DIR, 'raw_logs.jsonl')


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def compute_ttd():
    if not os.path.exists(MARKER):
        print('no demo marker found')
        return
    marker = json.load(open(MARKER, 'r', encoding='utf-8'))
    endpoint = marker['endpoint']
    start = datetime.fromisoformat(marker['start_time'].replace('Z',''))
    alerts = load_jsonl(ALERTS)
    # find first alert for endpoint
    first_alert = None
    for a in alerts:
        if a.get('endpoint') == endpoint:
            t = a.get('timestamp_range', {}).get('end')
            if t:
                first_alert = datetime.fromisoformat(t.replace('Z',''))
                break
    if not first_alert:
        print('no alert found for', endpoint)
        return
    ttd = (first_alert - start).total_seconds()
    print(f'First alert for {endpoint} at {first_alert.isoformat()} (TTD {ttd:.1f}s)')
    # false alert rate: total alerts / unique endpoints (simple)
    unique_endpoints = set(a.get('endpoint') for a in alerts)
    print(f'total alerts: {len(alerts)}, unique endpoints alerted: {len(unique_endpoints)}')

if __name__ == '__main__':
    compute_ttd()
