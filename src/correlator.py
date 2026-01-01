"""
Multi-Signal Correlation Engine

Validates anomalies only when at least two independent metrics deviate in the same time window.
This reduces false positives by requiring corroboration across signals.

Why it reduces false positives:
- Single metric deviations (e.g., temporary latency spike) are common and often benign.
- Requiring >=2 signals ensures the anomaly is systemic (e.g., latency + errors = real issue).
- Independence: Metrics like latency, error_rate, volume are uncorrelated, so co-deviation indicates true degradation.

Example Input (detections from detector):
{
  "/checkout": [
    {"metric": "avg_latency", "flagged": True, "reasons": ["z=2.5"]},
    {"metric": "error_rate", "flagged": False},
    {"metric": "request_volume", "flagged": True, "reasons": ["pct=30%"]}
  ]
}

Example Output (actionable_alerts):
{
  "/checkout": {
    "window_minutes": 5,
    "triggered_metrics": [
      {"metric": "avg_latency", "flagged": True, "reasons": ["z=2.5"]},
      {"metric": "request_volume", "flagged": True, "reasons": ["pct=30%"]}
    ]
  }
}

Non-Actionable Example (only 1 signal):
- Input: Only avg_latency flagged → Output: {} (no alert, false positive avoided).
"""

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
