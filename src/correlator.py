from typing import Dict, List, Any

# Correlator: requires at least two independent metric flags to mark actionable anomaly
MIN_SIGNALS = 2


def correlate(detections: Dict[str, List[Dict[str, Any]]]):
    """
    detections: endpoint -> list of metric detection dicts (from detector.detect)
    Returns: actionable_alerts: dict endpoint -> {window_minutes, triggered_metrics}
    """
    actionable = {}
    for endpoint, dets in detections.items():
        # count flagged independent signals
        flagged = [d for d in dets if d.get('flagged')]
        # ensure independence by metric name
        metrics = set(d['metric'] for d in flagged)
        if len(metrics) >= MIN_SIGNALS:
            # choose the most recent window_minutes among flagged
            window_minutes = max(d.get('window_minutes', 0) for d in flagged)
            actionable[endpoint] = {
                'window_minutes': window_minutes,
                'triggered_metrics': [d for d in flagged],
            }
    return actionable


if __name__ == '__main__':
    print('Correlator module loaded')
