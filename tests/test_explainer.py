import sys
from pathlib import Path

# Ensure src is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from explainer import explain


def test_explain_basic():
    alert = {
        "endpoint": "/checkout",
        "severity": "HIGH",
        "signals": [
            {"metric_name": "avg_latency", "baseline_value": 100.0, "current_value": 220.0, "deviation_ratio": 1.2},
            {"metric_name": "error_rate", "baseline_value": 0.005, "current_value": 0.02, "deviation_ratio": 3.0},
        ],
        "window_start": "2026-02-02T15:00:00Z",
        "window_end": "2026-02-02T15:01:00Z",
    }

    text = explain(alert)
    assert "/checkout" in text
    assert "avg_latency" in text
    assert "error rate" in text or "error_rate" in text
    assert "between 2026-02-02T15:00:00Z and 2026-02-02T15:01:00Z" in text
    assert "likely indicates degradation" in text
