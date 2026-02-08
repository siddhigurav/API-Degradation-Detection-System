#!/usr/bin/env python3
"""
Generate Demo Data for Dashboard

Creates sample metrics and alerts to demonstrate the dashboard functionality.
"""

import sys
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
ROOT = Path(__file__).resolve().parent  # Script is in project root
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))  # Also add the project root

from storage.metrics_store import get_metrics_store
from storage.alert_store import get_alert_store
from storage.baseline_store import get_baseline_store
from config import STORAGE_BACKEND

def generate_demo_data():
    """Generate sample metrics and alerts for dashboard demonstration."""
    print("🎯 Generating demo data for dashboard...")

    # Initialize stores
    metrics_store = get_metrics_store(STORAGE_BACKEND)
    alert_store = get_alert_store(STORAGE_BACKEND)
    baseline_store = get_baseline_store(STORAGE_BACKEND)

    # Generate metrics for the last 24 hours
    base_time = datetime.now(timezone.utc) - timedelta(hours=24)
    endpoints = ["/api/checkout", "/api/payment", "/api/user", "/api/search"]

    print("📊 Generating metrics data...")

    for hour in range(24):
        for minute in range(0, 60, 5):  # Every 5 minutes
            timestamp = base_time + timedelta(hours=hour, minutes=minute)

            for endpoint in endpoints:
                # Generate realistic metrics with some variation
                base_latency = {"checkout": 120, "payment": 100, "user": 80, "search": 90}[endpoint.split("/")[-1]]
                base_error = 0.005  # 0.5% baseline error rate

                # Add some degradation in the last few hours
                degradation_factor = 1.0
                if hour >= 20:  # Last 4 hours show degradation
                    degradation_factor = 1.0 + (hour - 19) * 0.1  # Gradual increase

                avg_latency = base_latency * degradation_factor + random.uniform(-10, 10)
                p95_latency = avg_latency * 1.5 + random.uniform(-5, 5)
                error_rate = base_error * degradation_factor + random.uniform(-0.001, 0.002)
                request_volume = 50 + random.randint(-10, 20)

                # Store metrics
                metrics_store.store_metrics([{
                    'endpoint': endpoint,
                    'window_minutes': 1,
                    'window_end': timestamp,
                    'avg_latency': max(10, avg_latency),
                    'p95_latency': max(15, p95_latency),
                    'error_rate': max(0, min(1, error_rate)),
                    'request_volume': max(1, request_volume),
                    'response_size_variance': 1000.0
                }])

    print("⚠️ Generating sample alerts...")

    # Generate some sample alerts
    alert_templates = [
        {
            "endpoint": "/api/checkout",
            "severity": "HIGH",
            "explanation": "Latency increased by 45.2% over recent period, primarily driven by 95th percentile latency drift. (moderate confidence)",
            "insights": ["Sustained latency degradation indicates performance regression", "Latency increase affecting user experience"],
            "recommendations": ["Profile application code for performance bottlenecks", "Check database query performance and indexes", "Monitor resource utilization (CPU, memory, disk)"]
        },
        {
            "endpoint": "/api/payment",
            "severity": "MEDIUM",
            "explanation": "Error rate increased from 0.5% → 2.1%. (low confidence)",
            "insights": ["Rising error rate causing failed requests"],
            "recommendations": ["Examine application logs for error patterns", "Check external service dependencies", "Verify configuration changes"]
        },
        {
            "endpoint": "/api/user",
            "severity": "CRITICAL",
            "explanation": "Latency increased by 78.3%, error rate increased from 0.3% → 4.2% over recent period. (high confidence)",
            "insights": ["Sustained latency degradation indicates performance regression", "Error rate trend suggests systemic issues", "Rising error rate causing failed requests"],
            "recommendations": ["Check recent deployments and database performance", "Review error logs for root cause patterns", "Consider rolling back recent changes", "URGENT: Investigate immediately - degradation just started"]
        }
    ]

    # Create alerts at different times
    for i, template in enumerate(alert_templates):
        alert_time = datetime.now(timezone.utc) - timedelta(hours=i*2)

        alert = dict(template)
        alert.update({
            "id": f"demo-alert-{i+1}",
            "created_at": alert_time.isoformat(),
            "window_start": (alert_time - timedelta(minutes=5)).isoformat(),
            "window_end": alert_time.isoformat(),
            "drift_context": {
                "latency_drift_score": 0.7 + i * 0.1,
                "error_drift_score": 0.4 + i * 0.15,
                "traffic_anomaly_score": 0.0
            },
            "signal_types": {
                "has_latency": "latency" in alert["explanation"].lower(),
                "has_error": "error" in alert["explanation"].lower(),
                "has_traffic": False
            }
        })

        alert_store.store_alert(alert)

    print("✅ Demo data generation complete!")
    print("📊 Run 'python dashboard.py' to view the dashboard")
    print("🌐 Open http://localhost:5000 in your browser")

if __name__ == "__main__":
    generate_demo_data()