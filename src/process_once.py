from datetime import datetime, timezone
from aggregator import compute_aggregates
from detector import detect
from correlator import correlate
from explainer import explain
from alerter import alert

if __name__ == '__main__':
    now = datetime.now(timezone.utc)
    aggregates = compute_aggregates(now=now)
    if not aggregates:
        print('no aggregates produced')
        exit(0)
    anomalies = detect(aggregates)
    if not anomalies:
        print('no anomalies detected')
        exit(0)

    actionable = correlate(anomalies)
    if not actionable:
        print('no actionable anomalies found')
        exit(0)

    for endpoint, info in actionable.items():
        triggered_anomalies = info['triggered_anomalies']
        explanation = explain(endpoint, triggered_anomalies)
        alert_obj = {
            'endpoint': endpoint,
            'severity': info['severity'],
            'explanation': explanation,
            'timestamp': now.isoformat().replace('+00:00', 'Z'),
            'window': info['window'],
            'anomaly_count': info['anomaly_count'],
            'anomalies': triggered_anomalies,
        }
        alert(alert_obj)
        print(f'alert emitted for {endpoint} ({info["severity"]} severity, {info["anomaly_count"]} anomalies)')
