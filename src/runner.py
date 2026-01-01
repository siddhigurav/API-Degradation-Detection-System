import time
from datetime import datetime
from aggregator import compute_aggregates
from detector import detect
from correlator import correlate
from explainer import explain
from alerter import alert

POLL_INTERVAL = 15  # seconds


def severity_from_metrics(triggered_metrics):
    # Deprecated: severity now handled in alerter.py
    return 'WARN'


def run_loop():
    print('Starting orchestration loop (ctrl-c to stop)')
    try:
        while True:
            now = datetime.utcnow()
            aggregates = compute_aggregates(now=now)
            if not aggregates:
                time.sleep(POLL_INTERVAL)
                continue
            dets = detect(aggregates)
            actionable = correlate(dets)
            for endpoint, info in actionable.items():
                triggered = info['triggered_metrics']
                explanation = explain(endpoint, triggered)
                severity = severity_from_metrics(triggered)
                alert_obj = {
                    'endpoint': endpoint,
                    'explanation': explanation,
                    'timestamp_range': {
                        'end': now.isoformat() + 'Z',
                        'minutes': info['window_minutes']
                    },
                    'triggered_metrics': triggered,
                }
                alert(alert_obj)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print('Stopping runner')


if __name__ == '__main__':
    run_loop()
