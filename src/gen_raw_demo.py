import os
import json
import random
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'data'))
RAW_LOGS = os.path.join(DATA_DIR, 'raw_logs.jsonl')

os.makedirs(DATA_DIR, exist_ok=True)
now = datetime.utcnow()

# write baseline (more volume)
with open(RAW_LOGS, 'w', encoding='utf-8') as fh:
    for i in range(50):
        t = now - timedelta(minutes=10, seconds=i*10)  # spread over 10m
        rec = {
            'timestamp': t.isoformat() + 'Z',
            'endpoint': '/checkout',
            'status_code': 200,
            'latency_ms': 120 + random.randint(-10,10),
            'response_size': 900,
            'error_message': None,
        }
        fh.write(json.dumps(rec) + '\n')
    # gradual latency over 50 points, spread over 5m
    for i in range(50):
        t = now - timedelta(minutes=5, seconds=i*6)  # 300s /50 =6s apart
        latency = 120 + (i * 20)  # grows to 1120
        rec = {
            'timestamp': t.isoformat() + 'Z',
            'endpoint': '/checkout',
            'status_code': 200 if i%10!=0 else 500,
            'latency_ms': latency,
            'response_size': 900,
            'error_message': None if i%10!=0 else 'err',
        }
        fh.write(json.dumps(rec) + '\n')
print('wrote', RAW_LOGS)
