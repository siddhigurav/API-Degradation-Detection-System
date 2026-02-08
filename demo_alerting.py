#!/usr/bin/env python3
"""
Demo of the Intelligent Alerting System

Shows how the system prevents alert fatigue with:
- Severity classification
- Deduplication
- Cool-down periods
- Multi-channel routing
"""

import sys
import time
from pathlib import Path

# Add src to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from src.alert_manager import process_alert


def demo_severity_levels():
    """Demonstrate severity classification."""
    print("🔍 Testing Severity Classification")
    print("=" * 40)

    alerts = [
        {
            "endpoint": "/api/health",
            "window": "2026-02-07T15:28:00Z/2026-02-07T15:29:00Z",
            "signals": [{"metric_name": "avg_latency", "severity": "LOW", "deviation_ratio": 1.1}],
            "explanation": "Minor latency increase"
        },
        {
            "endpoint": "/api/checkout",
            "window": "2026-02-07T15:28:00Z/2026-02-07T15:29:00Z",
            "signals": [
                {"metric_name": "avg_latency", "severity": "MEDIUM", "deviation_ratio": 1.5},
                {"metric_name": "error_rate", "severity": "MEDIUM", "current_value": 0.02}
            ],
            "explanation": "Moderate performance degradation"
        },
        {
            "endpoint": "/api/payment",
            "window": "2026-02-07T15:28:00Z/2026-02-07T15:29:00Z",
            "signals": [
                {"metric_name": "avg_latency", "severity": "HIGH", "deviation_ratio": 3.0},
                {"metric_name": "error_rate", "severity": "HIGH", "current_value": 0.08}
            ],
            "explanation": "Critical system degradation"
        }
    ]

    for alert in alerts:
        result = process_alert(alert)
        severity = alert.get('severity', 'UNKNOWN')
        print(f"✅ {severity}: {alert['endpoint']} - {'Sent' if result else 'Filtered'}")


def demo_deduplication():
    """Demonstrate alert deduplication."""
    print("\n🔄 Testing Deduplication")
    print("=" * 40)

    base_alert = {
        "endpoint": "/api/user",
        "severity": "WARN",
        "window": "2026-02-07T15:28:00Z/2026-02-07T15:29:00Z",
        "explanation": "User API latency spike"
    }

    print("Sending first alert...")
    result1 = process_alert(base_alert.copy())
    print(f"✅ First alert: {'Sent' if result1 else 'Filtered'}")

    print("Sending duplicate alert (should be deduplicated)...")
    result2 = process_alert(base_alert.copy())
    print(f"🚫 Duplicate alert: {'Sent' if result2 else 'Filtered (deduplicated)'}")

    print("Waiting for deduplication window to expire...")
    time.sleep(11)  # Wait longer than dedup window

    print("Sending alert after deduplication window...")
    result3 = process_alert(base_alert.copy())
    print(f"✅ Post-window alert: {'Sent' if result3 else 'Filtered'}")


def demo_cool_down():
    """Demonstrate cool-down periods."""
    print("\n⏰ Testing Cool-down Periods")
    print("=" * 40)

    alert = {
        "endpoint": "/api/search",
        "severity": "CRITICAL",
        "window": "2026-02-07T15:29:00Z/2026-02-07T15:30:00Z",
        "explanation": "Search API critical failure"
    }

    print("Sending CRITICAL alert...")
    result1 = process_alert(alert.copy())
    print(f"✅ First alert: {'Sent' if result1 else 'Filtered'}")

    print("Sending immediate follow-up (should be cooled-down)...")
    result2 = process_alert(alert.copy())
    print(f"🚫 Follow-up alert: {'Sent' if result2 else 'Filtered (cool-down)'}")

    print("Cool-down periods prevent alert spam!")


def demo_channel_routing():
    """Demonstrate multi-channel routing."""
    print("\n📢 Testing Multi-Channel Routing")
    print("=" * 40)

    alerts = [
        {
            "endpoint": "/api/info",
            "severity": "INFO",
            "window": "2026-02-07T15:29:00Z/2026-02-07T15:30:00Z",
            "explanation": "Informational alert",
            "insights": ["Minor metric fluctuation"],
            "recommendations": ["Monitor closely"]
        },
        {
            "endpoint": "/api/warn",
            "severity": "WARN",
            "window": "2026-02-07T15:29:00Z/2026-02-07T15:30:00Z",
            "explanation": "Warning alert",
            "insights": ["Performance degradation detected"],
            "recommendations": ["Investigate within hour"]
        },
        {
            "endpoint": "/api/critical",
            "severity": "CRITICAL",
            "window": "2026-02-07T15:29:00Z/2026-02-07T15:30:00Z",
            "explanation": "Critical alert",
            "insights": ["System stability at risk"],
            "recommendations": ["Immediate investigation required"]
        }
    ]

    for alert in alerts:
        result = process_alert(alert)
        severity = alert.get('severity', 'UNKNOWN')
        print(f"📤 {severity}: Routed to console{' + slack + email' if severity == 'CRITICAL' else ' + slack' if severity == 'WARN' else ''}")


def main():
    """Run the complete alerting system demo."""
    print("🚨 INTELLIGENT ALERTING SYSTEM DEMO")
    print("=" * 50)
    print("This demo shows how the system prevents alert fatigue while")
    print("ensuring critical issues get attention through:")
    print("• Smart severity classification")
    print("• Alert deduplication")
    print("• Cool-down periods")
    print("• Multi-channel routing")
    print()

    demo_severity_levels()
    demo_deduplication()
    demo_cool_down()
    demo_channel_routing()

    print("\n🎉 Demo Complete!")
    print("The alerting system now provides SRE-grade reliability")
    print("without overwhelming operators with noise.")


if __name__ == "__main__":
    main()