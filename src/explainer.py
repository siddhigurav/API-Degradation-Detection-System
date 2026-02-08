"""Explainer module

Converts an alert object into a concise, human-readable explanation.

Generates decision-grade narratives that engineers can act on, including:
- Specific metric changes with percentages and time ranges
- Confidence scores from drift analysis
- Primary drivers of degradation
- Clear time windows and durations

Public API:
    explain(alert: dict) -> str
    explain_alerts(alerts) -> list[dict]  # with explanation, insights, recommendations

No ML, no persistence. Pure Python, deterministic output.
"""

from typing import Dict, Any, List
from datetime import datetime, timezone
import math


def _fmt_percent(delta: float) -> str:
    return f"{delta * 100:.1f}%"


def _fmt_fold(baseline: float, current: float) -> str:
    try:
        if baseline == 0:
            return "∞"
        return f"{current / baseline:.1f}×"
    except Exception:
        return "?"


def _fmt_duration_minutes(start: str, end: str) -> str:
    """Calculate and format duration between ISO timestamps in minutes."""
    try:
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
        duration_minutes = (end_dt - start_dt).total_seconds() / 60
        if duration_minutes < 1:
            return f"{duration_minutes * 60:.0f} seconds"
        elif duration_minutes < 60:
            return f"{duration_minutes:.0f} minutes"
        else:
            hours = duration_minutes / 60
            return f"{hours:.1f} hours"
    except:
        return "recent period"


def _calculate_change_percentage(baseline: float, current: float) -> float:
    """Calculate percentage change from baseline to current."""
    if baseline == 0:
        return float('inf') if current > 0 else 0.0
    return ((current - baseline) / baseline)


def _get_primary_driver(signals: List[Dict[str, Any]]) -> str:
    """Identify the primary driver of the degradation."""
    # Sort by deviation ratio to find the most anomalous metric
    sorted_signals = sorted(signals, key=lambda s: abs(s.get('deviation_ratio', 0)), reverse=True)
    if not sorted_signals:
        return "multiple metrics"

    primary = sorted_signals[0]['metric_name']

    # Map to readable names
    if primary == 'avg_latency':
        return "average latency"
    elif primary == 'p95_latency':
        return "95th percentile latency"
    elif primary == 'error_rate':
        return "error rate"
    elif primary == 'request_volume':
        return "request volume"
    else:
        return primary.replace('_', ' ')


def _get_confidence_description(drift_context: Dict[str, Any]) -> str:
    """Generate confidence description from drift scores."""
    latency_score = drift_context.get('latency_drift_score', 0)
    error_score = drift_context.get('error_drift_score', 0)
    max_score = max(latency_score, error_score)

    if max_score > 0.8:
        return "high confidence"
    elif max_score > 0.5:
        return "moderate confidence"
    elif max_score > 0.2:
        return "low confidence"
    else:
        return "uncertain"


def explain(alert: Dict[str, Any]) -> str:
    """Generate a human-readable, decision-grade explanation for an alert.

    Creates narrative explanations like:
    "Latency for /login increased by 37% over 15 minutes, primarily driven by p95 latency drift.
     Error rate also increased from 0.2% → 1.4%."

    Uses templates based on signal combinations and includes confidence scores.
    """
    if not alert or not isinstance(alert, dict):
        return "No alert information provided."

    endpoint = alert.get("endpoint", "unknown endpoint")
    severity = alert.get("severity", "UNKNOWN")
    window_start = alert.get("window_start")
    window_end = alert.get("window_end")
    signals = list(alert.get("signals") or [])
    drift_context = alert.get("drift_context", {})
    signal_types = alert.get("signal_types", {})

    if not signals:
        return f"{severity} alert for {endpoint} — no signal details available."

    # Calculate time duration
    duration = "recent period"
    if window_start and window_end:
        duration = _fmt_duration_minutes(window_start, window_end)

    # Get confidence description
    confidence = _get_confidence_description(drift_context)

    # Build explanation based on signal types
    explanation_parts = []

    # Handle latency signals
    latency_signals = [s for s in signals if s.get('metric_name') in ['avg_latency', 'p95_latency']]
    if latency_signals:
        primary_latency = _get_primary_driver(latency_signals)
        latency_changes = []

        for signal in latency_signals:
            baseline = signal.get('baseline_value')
            current = signal.get('current_value')
            if baseline is not None and current is not None:
                pct_change = _calculate_change_percentage(baseline, current)
                if abs(pct_change) > 0.01:  # Only show significant changes
                    direction = "increased" if pct_change > 0 else "decreased"
                    latency_changes.append(f"{signal['metric_name'].replace('_', ' ')} {direction} by {_fmt_percent(abs(pct_change))}")

        if latency_changes:
            explanation_parts.append(f"Latency for {endpoint} {', '.join(latency_changes)} over {duration}")

            # Add primary driver if multiple latency metrics
            if len(latency_signals) > 1:
                primary_driver = _get_primary_driver(latency_signals)
                explanation_parts[-1] += f", primarily driven by {primary_driver} drift"

    # Handle error signals
    error_signals = [s for s in signals if s.get('metric_name') == 'error_rate']
    if error_signals:
        for signal in error_signals:
            baseline = signal.get('baseline_value')
            current = signal.get('current_value')
            if baseline is not None and current is not None:
                pct_change = _calculate_change_percentage(baseline, current)
                if abs(pct_change) > 0.01:
                    direction = "increased" if pct_change > 0 else "decreased"
                    baseline_pct = baseline * 100
                    current_pct = current * 100
                    explanation_parts.append(f"Error rate {direction} from {baseline_pct:.1f}% → {current_pct:.1f}%")

    # Handle traffic signals
    traffic_signals = [s for s in signals if s.get('metric_name') == 'request_volume']
    if traffic_signals:
        for signal in traffic_signals:
            baseline = signal.get('baseline_value')
            current = signal.get('current_value')
            if baseline is not None and current is not None:
                pct_change = _calculate_change_percentage(baseline, current)
                if abs(pct_change) > 0.01:
                    direction = "increased" if pct_change > 0 else "decreased"
                    explanation_parts.append(f"Request volume {direction} by {_fmt_percent(abs(pct_change))}")

    # Combine parts into final explanation
    if explanation_parts:
        main_explanation = ". ".join(explanation_parts)
        explanation = f"{main_explanation}."
    else:
        explanation = f"{severity} alert for {endpoint} over {duration} with {confidence}."

    # Add confidence if we have drift context
    if drift_context and any(drift_context.values()):
        explanation += f" ({confidence})"

    return explanation

def explain_alerts(alerts: Any) -> List[Dict[str, Any]]:
    """Produce explanations, insights and recommendations for alert(s).

    Accepts either a single alert dict or a list of alerts. Each returned
    item is a dict with `explanation`, `insights`, and `recommendations`.

    Enhanced to provide decision-grade narratives with specific actions.
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

        signal_types = a.get("signal_types", {})
        drift_context = a.get("drift_context", {})

        # Generate insights based on signal types and drift context
        if signal_types.get("has_latency"):
            latency_score = drift_context.get('latency_drift_score', 0)
            if latency_score > 0.5:
                insights.append("Sustained latency degradation indicates performance regression")
            else:
                insights.append("Latency increase affecting user experience")

        if signal_types.get("has_error"):
            error_score = drift_context.get('error_drift_score', 0)
            if error_score > 0.5:
                insights.append("Error rate trend suggests systemic issues")
            else:
                insights.append("Rising error rate causing failed requests")

        if signal_types.get("has_traffic"):
            insights.append("Traffic pattern changes may indicate external factors")

        # Generate specific recommendations
        if signal_types.get("has_latency") and signal_types.get("has_error"):
            recommendations.append("Check recent deployments and database performance")
            recommendations.append("Review error logs for root cause patterns")
            recommendations.append("Consider rolling back recent changes")

        elif signal_types.get("has_latency"):
            recommendations.append("Profile application code for performance bottlenecks")
            recommendations.append("Check database query performance and indexes")
            recommendations.append("Monitor resource utilization (CPU, memory, disk)")

        elif signal_types.get("has_error"):
            recommendations.append("Examine application logs for error patterns")
            recommendations.append("Check external service dependencies")
            recommendations.append("Verify configuration changes")

        if not recommendations:
            recommendations.append("Monitor the system closely and gather more diagnostic data")

        # Add time-based recommendations
        window_start = a.get("window_start")
        if window_start:
            try:
                alert_time = datetime.fromisoformat(window_start.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                time_since_alert = (now - alert_time).total_seconds() / 3600  # hours

                if time_since_alert < 1:
                    recommendations.insert(0, "URGENT: Investigate immediately - degradation just started")
                elif time_since_alert < 4:
                    recommendations.insert(0, "Investigate within next hour - degradation ongoing")
            except:
                pass

        # Deduplicate while preserving order
        insights = list(dict.fromkeys(insights)) or ["Performance degradation detected"]
        recommendations = list(dict.fromkeys(recommendations)) or ["Monitor the system and gather more data"]

        # Create result dict with original alert fields plus explanations
        result = dict(a)  # Copy all original fields
        result.update({
            "explanation": explanation,
            "insights": insights,
            "recommendations": recommendations,
        })

        results.append(result)

    return results


    return explanation


if __name__ == "__main__":
    # Test the enhanced explainer with a realistic alert
    example = {
        "endpoint": "/checkout",
        "severity": "HIGH",
        "signals": [
            {
                "metric_name": "avg_latency",
                "baseline_value": 100.0,
                "current_value": 220.0,
                "deviation_ratio": 1.2,
                "z_score": 3.5
            },
            {
                "metric_name": "p95_latency",
                "baseline_value": 150.0,
                "current_value": 350.0,
                "deviation_ratio": 1.33,
                "z_score": 4.2
            },
            {
                "metric_name": "error_rate",
                "baseline_value": 0.005,
                "current_value": 0.025,
                "deviation_ratio": 4.0,
                "z_score": 5.1
            },
        ],
        "window_start": "2026-02-02T15:00:00Z",
        "window_end": "2026-02-02T15:15:00Z",
        "drift_context": {
            "latency_drift_score": 0.85,
            "error_drift_score": 0.72,
            "traffic_anomaly_score": 0.1,
            "is_sustained_degradation": True
        },
        "signal_types": {
            "has_latency": True,
            "has_error": True,
            "has_traffic": False
        }
    }

    print("ENHANCED EXPLANATION ENGINE")
    print("=" * 50)
    explained = explain_alerts(example)
    result = explained[0]

    print(f"EXPLANATION: {result['explanation']}")
    print("\nINSIGHTS:")
    for insight in result['insights']:
        print(f"• {insight}")
    print("\nRECOMMENDATIONS:")
    for rec in result['recommendations']:
        print(f"• {rec}")


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