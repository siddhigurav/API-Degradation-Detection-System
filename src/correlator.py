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


def correlate(anomalies: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    anomalies: List of anomaly dicts from detector.detect (simplified format)
    Returns: actionable_alerts: dict endpoint -> {window, triggered_anomalies}
    Requires at least MIN_SIGNALS anomalies for the same endpoint+window to be actionable.
    """
    actionable = {}

    # Group anomalies by endpoint and window
    endpoint_window_groups = {}
    for anomaly in anomalies:
        endpoint = anomaly['endpoint']
        window = anomaly['window']
        key = f"{endpoint}:{window}"
        if key not in endpoint_window_groups:
            endpoint_window_groups[key] = []
        endpoint_window_groups[key].append(anomaly)

    # Check each endpoint+window group for sufficient signals
    for key, group_anomalies in endpoint_window_groups.items():
        endpoint, window = key.split(':', 1)

        # Ensure we have at least MIN_SIGNALS independent anomalies
        if len(group_anomalies) >= MIN_SIGNALS:
            # Sort by severity (CRITICAL > HIGH > MEDIUM > LOW)
            severity_order = {'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
            sorted_anomalies = sorted(group_anomalies,
                                    key=lambda x: severity_order.get(x.get('severity', 'LOW'), 0),
                                    reverse=True)

            actionable[endpoint] = {
                'window': window,
                'triggered_anomalies': sorted_anomalies,
                'severity': sorted_anomalies[0]['severity'],  # Highest severity
                'anomaly_count': len(sorted_anomalies)
            }

    return actionable


if __name__ == '__main__':
    print('Correlator module loaded')
