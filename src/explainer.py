"""
Explanation Generator

Converts anomaly data into human-readable alert messages.
Includes metric deltas (current vs baseline), baselines, time windows, and stable metrics.

Example Input: endpoint="/checkout", triggered_metrics=[{"metric": "avg_latency", "value": 500, "baseline_mean": 120, "pct_change": 3.17, "window_minutes": 15}]

Example Output: "avg latency for /checkout increased to 500ms (from baseline 120ms, +317%) over 15 minutes while error_rate and response_size_variance stayed stable."
"""

from typing import List, Dict, Any

METRIC_READABLE = {
    'avg_latency': 'avg latency',
    'p95_latency': 'p95 latency',
    'error_rate': 'error rate',
    'request_volume': 'request volume',
    'response_size_variance': 'response size variance',
}

ALL_METRICS = set(METRIC_READABLE.keys())


def explain(endpoint: str, anomalies: List[Dict[str, Any]]) -> str:
    """
    Generate natural language explanation for API degradation alerts.
    Includes metrics involved, direction & magnitude, time window, and stable signals.
    """
    if not anomalies:
        return f"No anomalies detected for {endpoint}."

    # Group anomalies by type for better narrative flow
    latency_anomalies = [a for a in anomalies if a['metric'] in ['avg_latency', 'p95_latency']]
    error_anomalies = [a for a in anomalies if a['metric'] == 'error_rate']
    volume_anomalies = [a for a in anomalies if a['metric'] == 'request_volume']
    variance_anomalies = [a for a in anomalies if a['metric'] == 'response_size_variance']

    window = anomalies[0].get('window', 'unknown')

    # Build the explanation narrative
    parts = []

    # Handle latency issues first (most critical)
    if latency_anomalies:
        latency_parts = []
        for anomaly in latency_anomalies:
            metric = anomaly['metric']
            name = 'p95 latency' if metric == 'p95_latency' else 'average latency'
            current = anomaly.get('current_value')
            baseline = anomaly.get('baseline_mean')

            if current is not None and baseline is not None:
                pct_change = ((current - baseline) / baseline) * 100
                direction = "increased" if pct_change > 0 else "decreased"
                latency_parts.append(f"{name} {direction} {abs(pct_change):.1f}% to {current:.1f}ms (from {baseline:.1f}ms)")

        if latency_parts:
            parts.append(" and ".join(latency_parts))

    # Handle error rate
    if error_anomalies:
        anomaly = error_anomalies[0]  # Take the first/highest priority
        current = anomaly.get('current_value')
        baseline = anomaly.get('baseline_mean')

        if current is not None and baseline is not None:
            direction = "rose" if current > baseline else "fell"
            parts.append(f"error rate {direction} from {baseline*100:.1f}% to {current*100:.1f}%")

    # Handle request volume
    if volume_anomalies:
        anomaly = volume_anomalies[0]
        current = anomaly.get('current_value')
        baseline = anomaly.get('baseline_mean')

        if current is not None and baseline is not None:
            pct_change = ((current - baseline) / baseline) * 100
            direction = "increased" if pct_change > 0 else "decreased"
            parts.append(f"request volume {direction} {abs(pct_change):.1f}% to {int(current)} (from {baseline:.1f})")

    # Handle response variance
    if variance_anomalies:
        anomaly = variance_anomalies[0]
        current = anomaly.get('current_value')
        baseline = anomaly.get('baseline_mean')

        if current is not None and baseline is not None:
            pct_change = ((current - baseline) / baseline) * 100
            direction = "increased" if pct_change > 0 else "decreased"
            parts.append(f"response size variance {direction} {abs(pct_change):.1f}%")

    # Identify stable metrics
    triggered_metrics = set(a['metric'] for a in anomalies)
    stable_metrics = [METRIC_READABLE[m] for m in ALL_METRICS - triggered_metrics]

    # Build the main explanation
    if parts:
        explanation = f"{' and '.join(parts)} for {endpoint} over {window}."

        # Add stable signals
        if stable_metrics:
            if len(stable_metrics) == 1:
                explanation += f" {stable_metrics[0].capitalize()} remained stable."
            else:
                explanation += f" {', '.join(stable_metrics[:-1])} and {stable_metrics[-1]} remained stable."

        # Add interpretation based on the pattern
        if latency_anomalies and error_anomalies and 'request_volume' not in triggered_metrics:
            explanation += " This indicates backend degradation rather than a traffic surge."
        elif latency_anomalies and 'request_volume' in triggered_metrics and 'error_rate' not in triggered_metrics:
            explanation += " This suggests traffic-related performance issues."
        elif error_anomalies and 'request_volume' not in triggered_metrics:
            explanation += " This points to service reliability problems."

        return explanation

    return f"Anomalies detected for {endpoint} over {window}, but unable to generate detailed explanation."


if __name__ == '__main__':
    print('Explainer module loaded')
