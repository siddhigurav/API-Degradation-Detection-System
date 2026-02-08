#!/usr/bin/env python3
"""Test script for drift detection system."""

import sys
import os

from src.storage.baseline_store import get_baseline_store
from src.storage.metrics_store import get_metrics_store
from src.detector import detect, calculate_drift_confidence_scores
from datetime import datetime, timedelta

def test_drift_detection():
    # Setup stores - use global instances to ensure consistency
    baseline_store = get_baseline_store()
    metrics_store = get_metrics_store(backend='memory')
    print(f"Test using metrics store: {id(metrics_store)}")

    # Establish baseline with normal metrics (with some variation)
    base_time = datetime.now()
    print("Establishing baseline...")
    for i in range(20):
        ts = base_time + timedelta(minutes=i)
        # Normal metrics with variation
        latency = 100.0 + (i % 3 - 1) * 5  # 95, 100, 105 pattern
        error = 0.01 + (i % 2) * 0.005     # 0.01, 0.015 pattern
        
        metrics_store.store_metrics([{
            'endpoint': '/api/test',
            'window_minutes': 1,
            'window_end': ts,
            'avg_latency': latency,
            'p95_latency': latency + 50,
            'error_rate': error,
            'request_volume': 100
        }])
        # Update baseline
        baseline_store.update_baseline('/api/test', 'avg_latency', latency, ts)
        baseline_store.update_baseline('/api/test', 'p95_latency', latency + 50, ts)
        baseline_store.update_baseline('/api/test', 'error_rate', error, ts)

    print('Baseline established')
    
    # Check baseline
    baseline = baseline_store.get_baseline('/api/test', 'avg_latency')
    print(f'Baseline for avg_latency: {baseline}')
    
    # Check recent metrics
    recent_metrics = metrics_store.get_metrics(endpoint='/api/test', window_minutes=1, start_time=base_time, end_time=datetime.now())
    print(f'Recent metrics count: {len(recent_metrics)}')
    print("Simulating degradation...")
    degradation_start = base_time + timedelta(minutes=20)
    for i in range(5):
        ts = degradation_start + timedelta(minutes=i)
        degraded_latency = 100.0 + (i + 1) * 50.0  # 150, 200, 250, 300, 350
        error = 0.01 + (i + 1) * 0.01  # increasing error rate

        metrics_store.store_metrics([{
            'endpoint': '/api/test',
            'window_minutes': 1,
            'window_end': ts,
            'avg_latency': degraded_latency,
            'p95_latency': degraded_latency + 50,
            'error_rate': error,
            'request_volume': 100
        }])
        # Update baseline with degraded values
        baseline_store.update_baseline('/api/test', 'avg_latency', degraded_latency, ts)
        baseline_store.update_baseline('/api/test', 'p95_latency', degraded_latency + 50, ts)
        baseline_store.update_baseline('/api/test', 'error_rate', error, ts)

    # Test detection
    aggregates = [{
        'endpoint': '/api/test',
        'window': '1m',
        'avg_latency': 350.0,  # Latest degraded value
        'p95_latency': 400.0,
        'error_rate': 0.06,
        'request_volume': 100,
        'timestamp': ts.isoformat() + 'Z'
    }]

    print(f"Passing aggregates to detect: {aggregates}")
    print("Running detection...")
    anomalies = detect(aggregates)
    print(f'Anomalies detected: {len(anomalies)}')
    for a in anomalies:
        print(f'Anomaly keys: {list(a.keys())}')
        print(f'  {a["metric_name"]}: {a["current_value"]:.1f} vs {a["baseline_value"]:.1f} (z={a["z_score"]:.2f})')
        drift_ctx = a.get("drift_context", {})
        print(f'  Sustained degradation: {drift_ctx.get("is_sustained_degradation", False)}')
        print(f'  Latency drift score: {drift_ctx.get("latency_drift_score", 0):.3f}')
        print(f'  Error drift score: {drift_ctx.get("error_drift_score", 0):.3f}')

    # Test the function directly
    print("\nTesting calculate_drift_confidence_scores directly...")
    scores = calculate_drift_confidence_scores('/api/test', aggregates)
    print(f'Direct call result: {scores}')

    # Debug: Check historical data
    print("\nDebugging historical data...")
    hist_df = metrics_store.get_metrics(
        endpoint='/api/test',
        window_minutes=1,
        start_time=base_time,
        end_time=ts + timedelta(minutes=1)
    )
    print(f'Historical metrics found: {len(hist_df)}')

    # Check all metrics in store
    all_df = metrics_store.get_metrics(endpoint='/api/test', window_minutes=1)
    print(f'All metrics for endpoint: {len(all_df)}')
    if not all_df.empty:
        print(f'Columns: {list(all_df.columns)}')
        print(f'Time range: {all_df["window_end"].min()} to {all_df["window_end"].max()}')
        print(f'Sample data:')
        print(all_df[['window_end', 'avg_latency', 'error_rate']].head())

if __name__ == '__main__':
    test_drift_detection()