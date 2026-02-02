"""Legacy detector (placeholder)

This file previously contained an older detector implementation. It has
been replaced with a small shim to avoid accidental import errors while
keeping the repository tidy.
"""

from typing import Dict, Any, List


def detect_anomalies(current_metrics: Dict[str, Any], baseline_metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Legacy stub: return empty list of anomalies."""
    return []
