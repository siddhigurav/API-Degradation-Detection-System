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


def explain(endpoint: str, triggered_metrics: List[Dict[str, Any]]):
    """
    Build a human-readable explanation for an alert.
    Includes deltas, baselines, time windows, and stable metrics.
    """
    if not triggered_metrics:
        return f"No anomalies detected for {endpoint}."

    parts = []
    window = triggered_metrics[0].get('window_minutes') if triggered_metrics else None
    for m in triggered_metrics:
        name = METRIC_READABLE.get(m['metric'], m['metric'])
        value = m.get('value')
        baseline = m.get('baseline_mean')
        pct = m.get('pct_change')
        delta = ''
        if value is not None and baseline is not None and not (isinstance(baseline, float) and (baseline != baseline)):
            if m['metric'] in ['avg_latency', 'p95_latency']:
                delta = f"to {value:.1f}ms (from baseline {baseline:.1f}ms"
            elif m['metric'] == 'error_rate':
                delta = f"to {value:.3f} (from baseline {baseline:.3f}"
            elif m['metric'] == 'request_volume':
                delta = f"to {int(value)} (from baseline {baseline:.1f}"
            else:
                delta = f"to {value:.1f} (from baseline {baseline:.1f}"
            if pct is not None and not (isinstance(pct, float) and (pct != pct)):
                sign = '+' if pct > 0 else ''
                delta += f", {sign}{pct*100:.1f}%)"
            else:
                delta += ")"
        elif pct is not None and not (isinstance(pct, float) and (pct != pct)):
            sign = '+' if pct > 0 else ''
            delta = f"{sign}{pct*100:.1f}%"
        elif 'z_score' in m:
            z = m.get('z_score')
            if z is not None and not (isinstance(z, float) and (z != z)):
                delta = f"z-score {z:.2f}"
        parts.append(f"{name} {delta}".strip())

    # Identify stable metrics (not in triggered)
    triggered_set = set(m['metric'] for m in triggered_metrics)
    stable = [METRIC_READABLE[m] for m in ALL_METRICS - triggered_set]
    stable_note = ''
    if stable:
        if len(stable) == 1:
            stable_note = f" while {stable[0]} stayed stable."
        else:
            stable_note = f" while {', '.join(stable[:-1])} and {stable[-1]} stayed stable."

    explanation = f"{'; '.join(parts)} for {endpoint} over {window} minute(s){stable_note}"
    return explanation


if __name__ == '__main__':
    print('Explainer module loaded')
