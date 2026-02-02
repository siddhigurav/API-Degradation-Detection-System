"""Explainer module

Converts an alert object into a concise, human-readable explanation.

Public API:
    explain(alert: dict) -> str

The function programmatically summarises which metrics changed, the
magnitude of change, the time window, and why the combination of signals
likely indicates degradation.

No ML, no persistence. Pure Python, deterministic output.
"""

from typing import Dict, Any, List


def _fmt_percent(delta: float) -> str:
    return f"{delta * 100:.1f}%"


def _fmt_fold(baseline: float, current: float) -> str:
    try:
        if baseline == 0:
            return "∞"
        return f"{current / baseline:.1f}×"
    except Exception:
        return "?"


def explain(alert: Dict[str, Any]) -> str:
    """Generate a human-readable explanation for `alert`.

    The function expects `alert` to contain `endpoint`, `severity`,
    `signals` (list of anomaly dicts with metric_name, baseline_value,
    current_value, deviation_ratio), and optional `window_start`/`window_end`.
    """
    if not alert or not isinstance(alert, dict):
        return "No alert information provided."

    endpoint = alert.get("endpoint", "unknown endpoint")
    severity = alert.get("severity", "UNKNOWN")
    window_start = alert.get("window_start")
    window_end = alert.get("window_end")

    if window_start and window_end:
        time_phrase = f"between {window_start} and {window_end}"
    elif window_start:
        time_phrase = f"starting at {window_start}"
    else:
        time_phrase = "in the recent window"

    signals: List[Dict[str, Any]] = list(alert.get("signals") or [])
    if not signals:
        return f"{severity} alert for {endpoint} {time_phrase} — no signal details available."

    metric_names = []
    parts: List[str] = []
    reasons: List[str] = []

    for s in signals:
        m = s.get("metric_name", "metric")
        metric_names.append(m)
        baseline = s.get("baseline_value")
        current = s.get("current_value")
        dev = s.get("deviation_ratio")

        mag = ""
        if baseline is not None and current is not None:
            if "error" in m or "rate" in m:
                try:
                    fold = _fmt_fold(float(baseline), float(current))
                    pct = _fmt_percent(float(dev)) if dev is not None else ""
                    mag = f"error rate rose from {baseline:.3f} to {current:.3f} ({fold}, {pct})"
                except Exception:
                    mag = "error rate increased"
            else:
                try:
                    pct = _fmt_percent(float(dev)) if dev is not None else ""
                    mag = f"from {baseline:.1f} to {current:.1f} ({pct})"
                except Exception:
                    mag = "changed noticeably"
        else:
            if dev is not None:
                try:
                    mag = f"changed by {_fmt_percent(float(dev))}"
                except Exception:
                    mag = "changed noticeably"
            else:
                mag = f"{s.get('severity', 'changed')}"

        parts.append(f"{m} {mag}")

        if m in ("avg_latency", "p95_latency") or "latency" in m:
            reasons.append("increased latency affects user experience")
        if "error" in m or "status" in m or "fail" in m:
            reasons.append("higher error rate causes failed requests")

    metrics_phrase = ", ".join(metric_names)
    details = "; ".join(parts)
    reason_phrase = " and ".join(sorted(set(reasons))) if reasons else "multiple signals indicate a problem"

    explanation = (
        f"{severity} alert for {endpoint} {time_phrase}: {metrics_phrase} changed ({details}). "
        f"This likely indicates degradation because {reason_phrase}."
    )

    return explanation


if __name__ == "__main__":
    example = {
        "endpoint": "/checkout",
        "severity": "HIGH",
        "signals": [
            {"metric_name": "avg_latency", "baseline_value": 100.0, "current_value": 220.0, "deviation_ratio": 1.2},
            {"metric_name": "error_rate", "baseline_value": 0.005, "current_value": 0.02, "deviation_ratio": 3.0},
        ],
        "window_start": "2026-02-02T15:00:00Z",
        "window_end": "2026-02-02T15:01:00Z",
    }

    print(explain(example))
def explain_alerts(alerts: Any) -> List[Dict[str, Any]]:
    """Produce explanations, insights and recommendations for alert(s).

    Accepts either a single alert dict or a list of alerts. Each returned
    item is a dict with `explanation`, `insights`, and `recommendations`.
    """
    if alerts is None:
        return []

    if not isinstance(alerts, list):
        alerts = [alerts]

    results: List[Dict[str, Any]] = []
    for a in alerts:
        explanation = explain(a)

        # Support both newer `signals` schema and older `anomalies` schema
        raw_signals = list(a.get("signals") or a.get("anomalies") or [])

        insights: List[str] = []
        recommendations: List[str] = []

        for s in raw_signals:
            name = (s.get("metric_name") or s.get("metric") or "").lower()

            if "latency" in name:
                insights.append("increased latency impacting user experience")
                recommendations.append("investigate backend performance and slow queries")

            if "error" in name or "status" in name or "fail" in name:
                insights.append("higher error rate causing failed requests")
                recommendations.append("check recent deployments and error logs")

            if "volume" in name or "request" in name:
                insights.append("traffic volume changed")
                recommendations.append("verify traffic sources and apply rate limiting if needed")

            if "response" in name or "variance" in name or "size" in name:
                insights.append("response size variance changed")
                recommendations.append("inspect payloads and caching behavior")

        # Deduplicate while preserving order
        insights = list(dict.fromkeys(insights)) or ["no specific insights"]
        recommendations = list(dict.fromkeys(recommendations)) or ["monitor the system and gather more data"]

        results.append({
            "explanation": explanation,
            "insights": insights,
            "recommendations": recommendations,
        })

    return results


if __name__ == "__main__":
    sample_alert = {
        "endpoint": "/checkout",
        "window": "5m",
        "severity": "CRITICAL",
        "anomaly_count": 2,
        "avg_deviation": 5.33,
        "max_deviation": 7.37,
        "anomalous_metrics": ["avg_latency", "p95_latency"],
        "anomalies": [
            {
                "metric": "avg_latency",
                "deviation": 7.37,
                "window": "5m",
                "severity": "CRITICAL",
                "endpoint": "/checkout",
                "current_value": 800.0,
                "baseline_mean": 120.0,
            },
            {
                "metric": "p95_latency",
                "deviation": 3.29,
                "window": "5m",
                "severity": "HIGH",
                "endpoint": "/checkout",
                "current_value": 850.0,
                "baseline_mean": 140.0,
            },
        ],
        "summary": "2 metrics anomalous on /checkout (5m window)",
    }

    explained = explain_alerts([sample_alert])
    print("EXPLANATION ENGINE OUTPUT:")
    print("=" * 50)
    print(explained[0]["explanation"])
    print("\nINSIGHTS:")
    for insight in explained[0]["insights"]:
        print(f"• {insight}")
    print("\nRECOMMENDATIONS:")
    for rec in explained[0]["recommendations"]:
        print(f"• {rec}")