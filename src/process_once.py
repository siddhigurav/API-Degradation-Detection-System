from datetime import datetime
from aggregator import compute_aggregates
from detector import detect
from correlator import correlate
from explainer import explain
from alerter import alert

if __name__ == '__main__':
    now = datetime.utcnow()
    aggregates = compute_aggregates(now=now)
    if not aggregates:
        print('no aggregates produced')
        exit(0)
    dets = detect(aggregates)
    actionable = correlate(dets)
    if not actionable:
        print('no actionable anomalies found')
    for endpoint, info in actionable.items():
        triggered = info['triggered_metrics']
        explanation = explain(endpoint, triggered)
        alert_obj = {
            'endpoint': endpoint,
            'severity': 'WARN',
            'explanation': explanation,
            'timestamp_range': {
                'end': now.isoformat() + 'Z',
                'minutes': info['window_minutes']
            },
            'triggered_metrics': triggered,
        }
        alert(alert_obj)
        print('alert emitted for', endpoint)
