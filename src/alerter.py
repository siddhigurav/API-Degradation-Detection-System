"""
Alerting Service

Outputs structured alerts to console and optionally Slack.
Includes severity classification: INFO (minor), WARN (moderate), CRITICAL (severe).

Severity Logic:
- CRITICAL: error_rate >10% or latency pct_change >100% or >3 signals.
- WARN: latency pct_change >50% or >2 signals.
- INFO: Otherwise.
"""

import os
import json
import time
import httpx
from typing import Dict, Any, List

SLACK_WEBHOOK = os.environ.get('SLACK_WEBHOOK_URL')
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'data'))
ALERTS_FILE = os.path.join(DATA_DIR, 'alerts.jsonl')


def classify_severity(anomalies: List[Dict[str, Any]]) -> str:
    """
    Classify alert severity based on anomalies.
    """
    if not anomalies:
        return 'INFO'
    
    num_signals = len(anomalies)
    has_high_error = any(a.get('metric') == 'error_rate' and a.get('current_value', 0) > 0.1 for a in anomalies)
    has_high_latency = any(a.get('metric') in ['avg_latency', 'p95_latency'] and abs(a.get('deviation', 0)) > 3.0 for a in anomalies)
    has_critical_severity = any(a.get('severity') == 'CRITICAL' for a in anomalies)
    
    if has_high_error or has_high_latency or num_signals > 3 or has_critical_severity:
        return 'CRITICAL'
    elif any(a.get('metric') in ['avg_latency', 'p95_latency'] and abs(a.get('deviation', 0)) > 2.0 for a in anomalies) or num_signals > 2:
        return 'WARN'
    else:
        return 'INFO'


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
    # Classify severity if not set
    if 'severity' not in alert_obj:
        anomalies = alert_obj.get('anomalies', [])
        alert_obj['severity'] = classify_severity(anomalies)
    
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
