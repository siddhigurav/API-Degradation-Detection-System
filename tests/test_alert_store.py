import os
import tempfile
import sys
import pathlib

# Ensure `src` package is importable when running tests from repo root
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'src'))
from storage.alert_store import AlertStore


def test_store_and_get_alert():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    try:
        store = AlertStore('sqlite', db_path=path)
        alert = {
            'endpoint': '/checkout',
            'severity': 'CRITICAL',
            'window': '12:00-12:05',
            'anomalous_metrics': [{'metric': 'p95_latency', 'baseline': '180ms', 'current': '470ms'}],
            'explanation': 'test',
        }
        aid = store.store_alert(alert)
        assert aid

        read = store.get_alert(aid)
        assert read is not None
        assert read['endpoint'] == '/checkout'
        assert read['severity'] == 'CRITICAL'
    finally:
        try:
            os.remove(path)
        except Exception:
            pass
