import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alerter_store import add_alert, get_alerts, get_alert


def test_add_and_get_alert():
    # Clear store by restarting module (simple approach for unit test isolation)
    # Note: tests run in single process; relying on fresh test environment is acceptable here.

    sample = {"endpoint": "/checkout", "severity": "HIGH", "signals": []}
    add_alert(sample)

    alerts = get_alerts()
    assert len(alerts) >= 1

    first = alerts[0]
    assert "id" in first
    aid = first["id"]

    fetched = get_alert(aid)
    assert fetched is not None
    assert fetched["id"] == aid
    assert fetched["endpoint"] == "/checkout"
