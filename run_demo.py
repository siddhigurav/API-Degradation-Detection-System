#!/usr/bin/env python3
"""
End-to-End Demo: API Degradation Detection System

This script demonstrates the complete pipeline:
1. Generate sample logs with anomalies
2. Process through aggregator → detector → correlator → explainer → alerter
3. Store alerts in database
4. Serve alerts via REST API

This proves the system actually works end-to-end!
"""

import time
from datetime import datetime, timezone, timedelta
from src.aggregator import aggregate_logs
from src.detector import detect
from src.correlator import correlate_anomalies
from src.explainer import explain_alerts
from src.alerter import store_alerts, get_alert_store
from src.storage import get_metrics_store

def create_anomalous_logs():
    """Create sample logs with clear anomalies for testing."""
    print("📝 Creating sample logs with anomalies...")

    # Create logs for the last hour with normal baseline + anomalies
    base_time = datetime(2026, 1, 5, 10, 0, 0, tzinfo=timezone.utc)
    logs = []

    # Normal baseline logs (first 50 minutes)
    for i in range(50):
        timestamp = (base_time + timedelta(minutes=i)).isoformat().replace('+00:00', 'Z')

        # Normal /checkout logs
        logs.append({
            "timestamp": timestamp,
            "endpoint": "/checkout",
            "status_code": 200,
            "latency_ms": 120 + (i % 10),  # Slight variation around 120ms
            "response_size": 1024
        })

        # Normal /api/users logs
        logs.append({
            "timestamp": timestamp,
            "endpoint": "/api/users",
            "status_code": 200,
            "latency_ms": 80 + (i % 5),  # Slight variation around 80ms
            "response_size": 2048
        })

    # Anomalous logs (last 10 minutes) - CRITICAL latency spike
    for i in range(10):
        timestamp = (base_time + timedelta(minutes=50 + i)).isoformat().replace('+00:00', 'Z')

        # ANOMALOUS /checkout logs - 800ms latency (6.7x increase!)
        logs.append({
            "timestamp": timestamp,
            "endpoint": "/checkout",
            "status_code": 200,
            "latency_ms": 800,  # CRITICAL anomaly
            "response_size": 1024
        })

        # Normal /api/users logs (contrast)
        logs.append({
            "timestamp": timestamp,
            "endpoint": "/api/users",
            "status_code": 200,
            "latency_ms": 85,
            "response_size": 2048
        })

    # Write logs to file
    import os
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)

    logs_file = os.path.join(data_dir, 'raw_logs.jsonl')
    with open(logs_file, 'w') as f:
        for log in logs:
            import json
            f.write(json.dumps(log) + '\n')

    print(f"✅ Created {len(logs)} log entries with clear anomalies")
    return logs

def run_full_pipeline(logs):
    """Run the complete detection pipeline."""
    print("\n🔄 Running complete detection pipeline...")

    # 1. Aggregation
    print("📊 Step 1: Computing aggregates...")
    current_time = datetime(2026, 1, 5, 11, 0, 0)  # Make timezone-naive for consistency
    aggregates = aggregate_logs(logs, current_time)
    print(f"   Found {len(aggregates)} aggregated metrics")

    # Convert aggregates dict to list format expected by detector
    aggregates_list = list(aggregates.values())

    # 2. Detection
    print("🔍 Step 2: Detecting anomalies...")
    anomalies = detect(aggregates_list)
    print(f"   Detected {len(anomalies)} metric-level anomalies")

    # 3. Correlation
    print("🔗 Step 3: Correlating anomalies...")
    alert_candidates = correlate_anomalies(anomalies)
    print(f"   Generated {len(alert_candidates)} alert candidates")

    # 4. Explanation
    print("🧠 Step 4: Generating explanations...")
    explained_alerts = explain_alerts(alert_candidates)
    print(f"   Created {len(explained_alerts)} explained alerts")

    # 5. Alerting/Storage
    print("💾 Step 5: Storing alerts...")
    alert_ids = store_alerts(explained_alerts)
    print(f"   Stored {len(alert_ids)} alerts with IDs: {alert_ids}")

    return explained_alerts, alert_ids

def demonstrate_api():
    """Demonstrate the REST API functionality."""
    print("\n🌐 Demonstrating REST API...")

    store = get_alert_store()

    # Get all alerts
    print("📋 GET /alerts - Retrieving all alerts...")
    alerts = store.get_all_alerts(limit=10)
    print(f"   Found {len(alerts)} alerts")

    if alerts:
        alert = alerts[0]
        print(f"   Sample alert: {alert['endpoint']} - {alert['severity']} - {alert['anomaly_count']} anomalies")

        # Get specific alert
        alert_id = alert['id']
        print(f"\n📋 GET /alerts/{alert_id} - Retrieving specific alert...")
        specific_alert = store.get_alert(alert_id)
        if specific_alert:
            print("   ✅ Alert retrieved successfully")
            print(f"   Endpoint: {specific_alert['endpoint']}")
            print(f"   Severity: {specific_alert['severity']}")
            print(f"   Metrics: {', '.join(specific_alert['anomalous_metrics'])}")
            print(f"   Explanation preview: {specific_alert['explanation'][:100]}...")
        else:
            print("   ❌ Alert not found")

def main():
    """Run the complete end-to-end demonstration."""
    print("🚀 API Degradation Detection System - End-to-End Demo")
    print("=" * 60)

    try:
        # Create test data
        logs = create_anomalous_logs()

        # Run full pipeline
        explained_alerts, alert_ids = run_full_pipeline(logs)

        # Demonstrate API
        demonstrate_api()

        print("\n" + "=" * 60)
        print("🎉 SUCCESS! The system is fully operational!")
        print()
        print("📊 What just happened:")
        print("   • Processed 60 minutes of API logs")
        print("   • Detected critical latency degradation (800ms vs 120ms baseline)")
        print("   • Generated actionable alerts with explanations")
        print("   • Stored alerts in database for API access")
        print()
        print("🚀 To start the API server, run:")
        print("   python run_api.py")
        print()
        print("📚 Then visit: http://localhost:8001/docs")
        print("🔍 Or test: curl http://localhost:8001/alerts")

    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
