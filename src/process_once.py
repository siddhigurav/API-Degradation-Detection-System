from datetime import datetime, timezone
from src.aggregator import compute_aggregates
from src.detector import detect
from src.correlator import correlate_anomalies
from src.explainer import explain_alerts
from src.alerter import store_alerts

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

    alert_candidates = correlate_anomalies(anomalies)
    if not alert_candidates:
        print('no alert candidates found')
        exit(0)

    explained_alerts = explain_alerts(alert_candidates)
    if not explained_alerts:
        print('no explained alerts generated')
        exit(0)

    alert_ids = store_alerts(explained_alerts)
    print(f'Successfully processed and stored {len(alert_ids)} alerts')
