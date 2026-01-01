import os
import json
import time
import httpx
from typing import Dict, Any

SLACK_WEBHOOK = os.environ.get('SLACK_WEBHOOK_URL')
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'data'))
ALERTS_FILE = os.path.join(DATA_DIR, 'alerts.jsonl')


def send_console(alert: Dict[str, Any]):
    ts = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    print('--- ALERT ---')
    print(f"time: {ts}")
    print(json.dumps(alert, indent=2))


def send_slack(alert: Dict[str, Any]):
    if not SLACK_WEBHOOK:
        return False
    text = f"*[{alert.get('severity','WARN')}]* {alert.get('endpoint')} - {alert.get('explanation')}"
    payload = {"text": text}
    try:
        r = httpx.post(SLACK_WEBHOOK, json=payload, timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False


def alert(alert_obj: Dict[str, Any]):
    # always print to console
    send_console(alert_obj)
    # persist alert for offline analysis
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(ALERTS_FILE, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(alert_obj) + '\n')
    except Exception:
        pass
    # try slack
    ok = send_slack(alert_obj)
    return ok


if __name__ == '__main__':
    print('Alerter module loaded; SLACK_WEBHOOK_URL set?' , bool(SLACK_WEBHOOK))
