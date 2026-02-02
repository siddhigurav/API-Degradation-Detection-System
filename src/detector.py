"""Detector - lightweight stub replacement.

This repository previously included a more complex detector implementation.
For cleanup purposes this file now provides a minimal, safe stub of the
public API so other modules can import it without failing during demos
or tests. It intentionally returns no anomalies.

If you need the original detector behavior restore from version control
or implement a detection algorithm in place of this stub.
"""

from typing import Dict, Any, List


def detect_anomalies(current_metrics: Dict[str, Any], baseline_metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return an empty anomaly list (stub).

    This keeps module imports and call sites working while removing the
    heavyweight detector implementation that is considered unnecessary.
    """
    return []
import logging
import math

logger = logging.getLogger(__name__)


def _severity_from_z(z: float) -> str:
    """Map z-score to severity label."""
    az = abs(z)
    if az >= 3.0:
        return "HIGH"
    if az >= 2.0:
        return "MEDIUM"
    if az >= 1.0:
        return "LOW"
    return "LOW"


def detect_anomalies(current_metrics: Dict[str, Dict[str, Dict[str, Any]]],
                     baseline_metrics: Dict[str, Dict[str, Dict[str, float]]]) -> List[Dict[str, Any]]:
    """Detect anomalies comparing current metrics to a provided baseline.

    Args:
        current_metrics: endpoint -> window_iso -> metrics dict.
        baseline_metrics: endpoint -> metric_name -> {"mean": float, "std": float}

    Returns:
        List of anomaly dicts.
    """
    anomalies: List[Dict[str, Any]] = []

    # Metrics we check
    metric_names = ("avg_latency", "p95_latency", "error_rate")

    for endpoint, windows in (current_metrics or {}).items():
        endpoint_baseline = baseline_metrics.get(endpoint, {})
        for window_start, metrics in (windows or {}).items():
            for m in metric_names:
                if m not in metrics:
                    continue

                current_value = metrics.get(m)
                baseline = endpoint_baseline.get(m)

                if baseline is None:
                    # No baseline available for this metric/endpoint -> skip
                    logger.debug("No baseline for %s %s %s", endpoint, window_start, m)
                    continue

                mean = baseline.get("mean")
                std = baseline.get("std")

                if mean is None or std is None:
                    logger.debug("Baseline missing fields for %s %s %s", endpoint, window_start, m)
                    continue

                # Defensive numeric coercion
                try:
                    current_num = float(current_value)
                    mean_num = float(mean)
                    std_num = float(std)
                except Exception:
                    logger.debug("Non-numeric values for %s %s %s", endpoint, window_start, m)
                    continue

                # Compute deviation metrics
                # z-score (use std if available, otherwise use relative difference)
                if std_num > 0:
                    z = (current_num - mean_num) / std_num
                else:
                    # if std is zero, fall back to relative change
                    z = (current_num - mean_num) / (abs(mean_num) if mean_num != 0 else 1.0)

                # deviation_ratio: fractional change relative to mean
                deviation_ratio = (current_num - mean_num) / (abs(mean_num) if mean_num != 0 else 1.0)

                severity = _severity_from_z(z)

                # Decide whether this is an anomaly: use |z| >= 1.0 as threshold
                is_anomaly = abs(z) >= 1.0

                logger.debug(
                    "Detect %s %s %s: current=%s mean=%s std=%s z=%.2f dev=%.3f anomaly=%s",
                    endpoint, window_start, m, current_num, mean_num, std_num, z, deviation_ratio, is_anomaly
                )

                if is_anomaly:
                    anomaly = {
                        "endpoint": endpoint,
                        "window_start": window_start,
                        "metric_name": m,
                        "baseline_value": mean_num,
                        "current_value": current_num,
                        "deviation_ratio": round(deviation_ratio, 4),
                        "severity": severity,
                    }
                    logger.info("Anomaly detected: %s", anomaly)
                    anomalies.append(anomaly)

    return anomalies


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)

    # Minimal usage example
    current = {
        "/checkout": {
            "2026-02-02T15:00:00Z": {"avg_latency": 160.0, "p95_latency": 300.0, "error_rate": 0.02}
        }
    }

    baseline = {
        "/checkout": {
            "avg_latency": {"mean": 100.0, "std": 10.0},
            "p95_latency": {"mean": 180.0, "std": 20.0},
            "error_rate": {"mean": 0.005, "std": 0.002},
        }
    }

    print(detect_anomalies(current, baseline))
