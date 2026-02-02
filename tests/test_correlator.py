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

    # Only one alert (for /checkout) should be produced
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["endpoint"] == "/checkout"
    assert alert["severity"] == "HIGH"  # max of HIGH and MEDIUM
    assert len(alert["signals"]) == 2
    assert alert["window_start"] == "2026-02-02T15:00:00Z"
    assert alert["window_end"] == "2026-02-02T15:01:00Z"
