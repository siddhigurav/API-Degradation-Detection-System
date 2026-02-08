import sys
from pathlib import Path

# Ensure src is importable when running tests from repo root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from detector import detect_anomalies


def test_detect_anomalies_basic():
    current = {
        "/checkout": {
            "2026-02-02T15:00:00Z": {"avg_latency": 160.0, "p95_latency": 300.0, "error_rate": 0.02}
        }
    }

    baseline = {
        "/checkout": {
            "avg_latency": {"mean": 100.0, "std": 10.0, "ewma": 100.0, "ewma_std": 10.0, "count": 20},
            "p95_latency": {"mean": 180.0, "std": 20.0, "ewma": 180.0, "ewma_std": 20.0, "count": 20},
            "error_rate": {"mean": 0.005, "std": 0.002, "ewma": 0.005, "ewma_std": 0.002, "count": 20},
        }
    }

    anomalies = detect_anomalies(current, baseline)

    # Should detect at least avg_latency as HIGH (z = 6)
    names = {a["metric_name"] for a in anomalies}
    assert "avg_latency" in names
