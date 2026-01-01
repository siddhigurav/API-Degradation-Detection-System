import time
import json
from datetime import datetime
from failure_injector import gradual_latency, partial_timeouts, response_size_inflation
import os

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
MARKER = os.path.join(DATA_DIR, 'demo_marker.json')

os.makedirs(DATA_DIR, exist_ok=True)

def write_marker(endpoint, scenario):
    m = {
        'endpoint': endpoint,
        'scenario': scenario,
        'start_time': datetime.utcnow().isoformat() + 'Z'
    }
    with open(MARKER, 'w', encoding='utf-8') as fh:
        json.dump(m, fh)
    return m

if __name__ == '__main__':
    print('Running demo: baseline traffic then injected degradation')
    # baseline: a few normal requests
    endpoint = '/checkout'
    write_marker(endpoint, 'gradual_latency')
    print('sending brief baseline...')
    for _ in range(10):
        # send a few normal requests
        from failure_injector import send_log
        send_log(endpoint=endpoint, latency=120, status=200, size=900)
        time.sleep(0.2)
    print('starting gradual latency injection...')
    # run a faster, shorter gradual latency so demo finishes quickly
    gradual_latency(endpoint=endpoint, start=120, end=1500, steps=30, interval=0.5)
    print('injection finished; allow system to stabilize for 10s')
    time.sleep(10)
    print('demo complete')
