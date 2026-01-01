from typing import List, Dict, Any

METRIC_READABLE = {
    'avg_latency': 'avg latency',
    'p95_latency': 'p95 latency',
    'error_rate': 'error rate',
    'request_volume': 'request volume',
    'response_size_variance': 'response size variance',
}


def explain(endpoint: str, triggered_metrics: List[Dict[str, Any]]):
    """
    Build a human-readable explanation for an alert.
    Example:
    “p95 latency for /checkout increased 41% over 15 minutes while request volume stayed stable.”
    """
    parts = []
    window = triggered_metrics[0].get('window_minutes') if triggered_metrics else None
    for m in triggered_metrics:
        name = METRIC_READABLE.get(m['metric'], m['metric'])
        pct = m.get('pct_change')
        reason = ''
        if pct is not None and not (isinstance(pct, float) and (pct != pct)):
            try:
                reason = f"increased {abs(pct)*100:.1f}%" if pct > 0 else f"decreased {abs(pct)*100:.1f}%"
            except Exception:
                reason = ''
        elif 'z_score' in m:
            z = m.get('z_score')
            if z is not None and not (isinstance(z, float) and (z != z)):
                reason = f"z-score {z:.2f}"
        parts.append(f"{name} {reason}".strip())
    # Simple heuristic: check request_volume metric presence to comment on volume
    volume_metrics = [m for m in triggered_metrics if m['metric'] == 'request_volume']
    volume_note = ''
    if not volume_metrics:
        volume_note = 'request volume stayed stable.'
    else:
        volume_note = 'request volume changed.'
    explanation = f"{'; '.join(parts)} for {endpoint} over {window} minute(s) while {volume_note}"
    return explanation


if __name__ == '__main__':
    print('Explainer module loaded')
