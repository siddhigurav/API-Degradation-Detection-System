import time
import random
import requests
import os
import json
from datetime import datetime

INGEST_URL = 'http://localhost:8000/ingest'
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'data'))
RAW_LOGS = os.path.join(DATA_DIR, 'raw_logs.jsonl')


def send_log(endpoint='/checkout', status=200, latency=100.0, size=1024, err=None):
    payload = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'endpoint': endpoint,
        'status_code': status,
        'latency_ms': latency,
        'response_size': size,
        'error_message': err,
    }
    try:
        requests.post(INGEST_URL, json=payload, timeout=2)
    except Exception:
        # fallback: write directly to raw logs so the demo can run without a live ingest service
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(RAW_LOGS, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(payload) + '\n')
        except Exception:
            pass


def gradual_latency(endpoint='/checkout', start=100, end=2000, steps=60, interval=1.0):
    step = (end - start) / max(1, steps)
    cur = start
    for i in range(steps):
        send_log(endpoint=endpoint, latency=cur, status=200, size=1000)
        cur += step
        time.sleep(interval)


def partial_timeouts(endpoint='/search', total=60, p_timeout=0.1, interval=1.0):
    for i in range(total):
        if random.random() < p_timeout:
            send_log(endpoint=endpoint, latency=3000, status=504, size=0, err='timeout')
        else:
            send_log(endpoint=endpoint, latency=120, status=200, size=800)
        time.sleep(interval)


def response_size_inflation(endpoint='/items', factor=5, bursts=10, interval=2.0):
    for i in range(bursts):
        send_log(endpoint=endpoint, latency=120, status=200, size=1000 * factor)
        time.sleep(interval)


if __name__ == '__main__':
    # quick demo runner
    print('Starting failure injection demo: gradual latency on /checkout')
    gradual_latency()
    print('done')
