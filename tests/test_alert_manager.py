import sys
from pathlib import Path

# Ensure src is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alert_manager import AlertManager, process_alert


def test_alert_manager_severity_classification():
    """Test severity classification logic."""
    manager = AlertManager()

    # Test INFO level
    info_alert = {
        'endpoint': '/test',
        'signals': [{'metric_name': 'avg_latency', 'severity': 'LOW'}]
    }
    assert manager.classify_severity(info_alert) == 'INFO'

    # Test WARN level
    warn_alert = {
        'endpoint': '/test',
        'signals': [
            {'metric_name': 'avg_latency', 'severity': 'MEDIUM', 'deviation_ratio': 1.5},
            {'metric_name': 'error_rate', 'severity': 'MEDIUM', 'current_value': 0.02}
        ]
    }
    assert manager.classify_severity(warn_alert) == 'WARN'

    # Test CRITICAL level
    critical_alert = {
        'endpoint': '/test',
        'signals': [
            {'metric_name': 'avg_latency', 'severity': 'HIGH', 'deviation_ratio': 3.0},
            {'metric_name': 'error_rate', 'severity': 'HIGH', 'current_value': 0.1}
        ]
    }
    assert manager.classify_severity(critical_alert) == 'CRITICAL'


def test_alert_manager_deduplication():
    """Test alert deduplication."""
    manager = AlertManager()

    alert1 = {
        'endpoint': '/test',
        'severity': 'WARN',
        'explanation': 'Test alert 1'
    }

    alert2 = {
        'endpoint': '/test',
        'severity': 'WARN',
        'explanation': 'Test alert 2'
    }

    # First alert should be processed
    result1 = manager.process_alert(alert1)
    assert result1 == True

    # Second alert should be deduplicated (within dedup window)
    result2 = manager.process_alert(alert2)
    assert result2 == False


def test_alert_manager_cooldown():
    """Test cool-down periods."""
    manager = AlertManager()

    # Clear any existing tracking
    manager.clear_cooldowns()

    alert = {
        'endpoint': '/test',
        'severity': 'CRITICAL',
        'explanation': 'Test alert'
    }

    # First alert should be processed
    result1 = manager.process_alert(alert)
    assert result1 == True

    # Second alert should be blocked by cool-down
    result2 = manager.process_alert(alert)
    assert result2 == False


def test_process_alert_integration():
    """Test the global process_alert function."""
    alert = {
        'endpoint': '/test',
        'signals': [{'metric_name': 'avg_latency', 'severity': 'HIGH'}],
        'explanation': 'Test alert'
    }

    # Should process successfully
    result = process_alert(alert)
    assert isinstance(result, bool)


if __name__ == '__main__':
    test_alert_manager_severity_classification()
    test_alert_manager_deduplication()
    test_alert_manager_cooldown()
    test_process_alert_integration()
    print("All alert manager tests passed!")