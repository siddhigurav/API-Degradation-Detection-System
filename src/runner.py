import time
from datetime import datetime
from storage.metrics_store import InMemoryMetricsStorage
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
    metrics_store = InMemoryMetricsStorage()
    try:
        while True:
            now = datetime.utcnow()
            
            # Get latest metrics from storage
            latest_metrics_df = metrics_store.get_latest_metrics()
            if latest_metrics_df.empty:
                time.sleep(POLL_INTERVAL)
                continue
            
            # Convert to aggregates format
            aggregates = []
            for _, row in latest_metrics_df.iterrows():
                agg = {
                    'endpoint': row['endpoint'],
                    'window': f"{row['window_minutes']}m",
                    'avg_latency': row['avg_latency'],
                    'p95_latency': row['p95_latency'],
                    'error_rate': row['error_rate'],
                    'request_volume': row['request_volume'],
                    'timestamp': row['timestamp'].isoformat().replace('+00:00', 'Z') if hasattr(row['timestamp'], 'isoformat') else str(row['timestamp'])
                }
                aggregates.append(agg)
            
            if not aggregates:
                time.sleep(POLL_INTERVAL)
                continue
                
            dets = detect(aggregates)
            alerts = correlate(dets)
            for alert in alerts:
                explanation = explain(alert)
                alert_obj = {
                    'endpoint': alert['endpoint'],
                    'severity': alert['severity'],
                    'anomalous_metrics': [signal['metric_name'] for signal in alert['signals']],
                    'explanation': explanation,
                    'timestamp_range': {
                        'end': alert['window_end'],
                        'minutes': 0  # TODO: calculate from window
                    },
                    'anomalies': alert['signals'],  # Add the full signals
                }
                alert(alert_obj)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print('Stopping runner')


if __name__ == '__main__':
    run_loop()
