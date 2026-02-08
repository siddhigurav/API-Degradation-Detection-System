import sys
from pathlib import Path

# Ensure src is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from correlator import correlate


def test_correlate_creates_alert_for_two_signals():
    anomalies = [
        {
            "endpoint": "/checkout",
            "window_start": "2026-02-02T15:00:00Z",
            "metric_name": "avg_latency",
            "severity": "HIGH",
            "deviation_ratio": 1.0,
        },
        {
            "endpoint": "/checkout",
            "window_start": "2026-02-02T15:00:00Z",
            "metric_name": "error_rate",
            "severity": "MEDIUM",
            "deviation_ratio": 2.0,
        },
        # Single-signal endpoint should not produce an alert
        {
            "endpoint": "/login",
            "window_start": "2026-02-02T15:01:00Z",
            "metric_name": "avg_latency",
            "severity": "LOW",
            "deviation_ratio": 0.2,
        },
    ]

    alerts = correlate(anomalies)

    # Two alerts should be produced (one for /checkout with 2 signals, one for /login with 1 signal)
    assert len(alerts) == 2
    
    # Check the /checkout alert
    checkout_alert = next(a for a in alerts if a["endpoint"] == "/checkout")
    assert checkout_alert["severity"] == "HIGH"  # Latency + Error = HIGH
    assert len(checkout_alert["signals"]) == 2
    assert checkout_alert["window_start"] == "2026-02-02T15:00:00Z"
    assert checkout_alert["signal_types"]["has_latency"] == True
    assert checkout_alert["signal_types"]["has_error"] == True
    assert checkout_alert["signal_types"]["has_traffic"] == False
    
    # Check the /login alert
    login_alert = next(a for a in alerts if a["endpoint"] == "/login")
    assert login_alert["severity"] == "MEDIUM"  # Single latency signal
    assert len(login_alert["signals"]) == 1


def test_correlate_latency_only_medium_severity():
    anomalies = [
        {
            "endpoint": "/api",
            "window_start": "2026-02-02T15:00:00Z",
            "metric_name": "avg_latency",
            "severity": "MEDIUM",
        },
        {
            "endpoint": "/api",
            "window_start": "2026-02-02T15:00:00Z",
            "metric_name": "p95_latency",
            "severity": "MEDIUM",
        },
    ]

    alerts = correlate(anomalies)

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["severity"] == "MEDIUM"  # Latency only = MEDIUM
    assert alert["signal_types"]["has_latency"] == True
    assert alert["signal_types"]["has_error"] == False


def test_correlate_error_only_medium_severity():
    anomalies = [
        {
            "endpoint": "/api",
            "window_start": "2026-02-02T15:00:00Z",
            "metric_name": "error_rate",
            "severity": "HIGH",
        },
        {
            "endpoint": "/api",
            "window_start": "2026-02-02T15:00:00Z",
            "metric_name": "error_rate",
            "severity": "HIGH",
        },
    ]

    alerts = correlate(anomalies)

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["severity"] == "MEDIUM"  # Error only = MEDIUM
    assert alert["signal_types"]["has_error"] == True
    assert alert["signal_types"]["has_latency"] == False


def test_correlate_single_signal_suppressed():
    anomalies = [
        {
            "endpoint": "/api",
            "window_start": "2026-02-02T15:00:00Z",
            "metric_name": "avg_latency",
            "severity": "HIGH",
        },
    ]

    alerts = correlate(anomalies)

    assert len(alerts) == 1  # Single signal now produces an alert
    assert alerts[0]["endpoint"] == "/api"
    assert alerts[0]["severity"] == "MEDIUM"  # Single latency signal


def test_correlate_traffic_only_suppressed():
    anomalies = [
        {
            "endpoint": "/api",
            "window_start": "2026-02-02T15:00:00Z",
            "metric_name": "request_volume",
            "severity": "HIGH",
        },
        {
            "endpoint": "/api",
            "window_start": "2026-02-02T15:00:00Z",
            "metric_name": "request_volume",
            "severity": "HIGH",
        },
    ]

    alerts = correlate(anomalies)

    assert len(alerts) == 0  # Traffic only suppressed (no latency or error)
