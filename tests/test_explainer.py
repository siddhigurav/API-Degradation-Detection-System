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
        "drift_context": {"latency_drift_score": 0.6, "error_drift_score": 0.4},
        "signal_types": {"has_latency": True, "has_error": True, "has_traffic": False}
    }

    text = explain(alert)
    assert "/checkout" in text
    assert "increased by 120.0%" in text or "increased by 120%" in text
    assert "Error rate increased from 0.5% → 2.0%" in text
    assert "1 minutes" in text or "over" in text
    assert "moderate confidence" in text
