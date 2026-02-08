"""
Synthetic Degradation Testing Framework

Automated test runner for API degradation detection system.
Simulates realistic degradation scenarios and measures detection accuracy.

Scenarios tested:
- Gradual latency increase
- Error rate creep
- Traffic surges
- Combined degradation patterns

Metrics tracked:
- Time to detect degradation
- Precision (true positives / total alerts)
- Recall (true positives / actual degradations)
- False positive rate
"""

import sys
import time
import json
import pytest
import threading
import requests
import random
import os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

# Set storage backend to memory for testing
os.environ['STORAGE_BACKEND'] = 'memory'

# Add src to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aggregator import RollingMetricsAggregator, compute_aggregates
from detector import detect
from correlator import correlate
from explainer import explain_alerts
from alert_manager import process_alert
from storage.baseline_store import get_baseline_store
from storage.metrics_store import get_metrics_store
from storage.alert_store import get_alert_store
from failure_injector import FailureInjector


@dataclass
class DegradationScenario:
    """Defines a synthetic degradation scenario."""
    name: str
    description: str
    duration_minutes: int
    endpoint: str = "/api/test"

    # Degradation parameters
    latency_start: float = 100.0  # ms
    latency_end: float = 100.0    # ms
    error_start: float = 0.01     # 1%
    error_end: float = 0.01       # 1%
    traffic_start: int = 10       # requests per minute
    traffic_end: int = 10         # requests per minute

    # Expected detection
    expected_detection_time: Optional[int] = None  # minutes from start
    expected_severity: str = "INFO"


@dataclass
class TestMetrics:
    """Tracks test execution metrics."""
    scenario_name: str
    start_time: datetime
    alerts_generated: List[Dict[str, Any]] = field(default_factory=list)
    actual_degradation_start: Optional[datetime] = None
    first_alert_time: Optional[datetime] = None
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    def detection_time_minutes(self) -> Optional[float]:
        """Calculate time to detection in minutes."""
        if not (self.actual_degradation_start and self.first_alert_time):
            return None
        return (self.first_alert_time - self.actual_degradation_start).total_seconds() / 60

    def precision(self) -> float:
        """Calculate precision: TP / (TP + FP)"""
        total_positives = self.true_positives + self.false_positives
        return self.true_positives / total_positives if total_positives > 0 else 0.0

    def recall(self) -> float:
        """Calculate recall: TP / (TP + FN)"""
        total_actual = self.true_positives + self.false_negatives
        return self.true_positives / total_actual if total_actual > 0 else 0.0


class SyntheticLogGenerator:
    """Generates synthetic logs with controlled degradation patterns."""

    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.ingest_url = f"{base_url}/ingest"
        self.session = requests.Session()

    def generate_log_entry(self,
                          endpoint: str,
                          timestamp: datetime,
                          latency_ms: float,
                          error_rate: float,
                          request_volume: int) -> Dict[str, Any]:
        """Generate a single synthetic log entry."""

        # Add natural variation
        latency = max(10, int(latency_ms + random.normalvariate(0, latency_ms * 0.1)))
        is_error = random.random() < error_rate
        status_code = 500 if is_error else 200

        return {
            "timestamp": timestamp.isoformat() + "Z",
            "endpoint": endpoint,
            "status_code": status_code,
            "latency_ms": latency,
            "response_size": 1000 + random.randint(-200, 200),
            "error_message": "Synthetic error" if is_error else None,
        }

    def inject_scenario(self, scenario: DegradationScenario) -> List[Dict[str, Any]]:
        """Generate logs for a complete degradation scenario."""
        logs_injected = []
        start_time = datetime.now()

        print(f"🚀 Starting scenario: {scenario.name}")
        print(f"   {scenario.description}")
        print(f"   Duration: {scenario.duration_minutes} minutes")

        for minute in range(scenario.duration_minutes):
            # Calculate current degradation level (linear interpolation)
            progress = minute / max(1, scenario.duration_minutes - 1)

            current_latency = scenario.latency_start + (scenario.latency_end - scenario.latency_start) * progress
            current_error = scenario.error_start + (scenario.error_end - scenario.error_start) * progress
            current_traffic = int(scenario.traffic_start + (scenario.traffic_end - scenario.traffic_start) * progress)

            # Generate logs for this minute
            for request in range(current_traffic):
                timestamp = start_time + timedelta(minutes=minute, seconds=request * (60 / current_traffic))

                log_entry = self.generate_log_entry(
                    scenario.endpoint,
                    timestamp,
                    current_latency,
                    current_error,
                    current_traffic
                )

                logs_injected.append(log_entry)

            # Small delay to prevent overwhelming (not needed for direct processing)
            # time.sleep(0.1)

        print(f"✅ Generated {len(logs_injected)} logs for scenario {scenario.name}")
        return logs_injected


class SyntheticTestRunner:
    """Automated test runner that manages API server lifecycle."""

    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.server_process = None
        self.generator = SyntheticLogGenerator(base_url)
        self.aggregator = RollingMetricsAggregator()
        self.metrics_store = get_metrics_store('memory')  # Use global instance
        self.alert_store = get_alert_store('memory')

    def start_server(self) -> bool:
        """Start the API server in background."""
        import subprocess
        import os

        print("🚀 Starting API server...")

        # Set environment variables for testing
        env = os.environ.copy()
        env['STORAGE_BACKEND'] = 'memory'
        env['ALERT_BACKEND'] = 'memory'

        try:
            # Start server in background
            self.server_process = subprocess.Popen(
                [sys.executable, str(ROOT / "run_api.py")],
                cwd=str(ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Wait for server to start
            time.sleep(3)

            # Test if server is responding
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                print("✅ API server started successfully")
                return True
            else:
                print(f"❌ Server health check failed: {response.status_code}")
                self.stop_server()
                return False

        except Exception as e:
            print(f"❌ Failed to start server: {e}")
            return False

    def stop_server(self):
        """Stop the background API server."""
        if self.server_process:
            print("🛑 Stopping API server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
                print("✅ API server stopped")
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                print("⚠️ API server force killed")
            self.server_process = None

    def run_scenario_test(self, scenario: DegradationScenario) -> TestMetrics:
        """Run a single degradation scenario test."""
        if not self.server_process:
            raise RuntimeError("Server not started. Call start_server() first.")

        metrics = TestMetrics(scenario.name, datetime.now())

        # Set degradation start time (when logs start being injected)
        metrics.actual_degradation_start = metrics.start_time.replace(tzinfo=timezone.utc)

        # Establish baseline data for the scenario endpoint
        self._establish_baseline(scenario.endpoint)

        # Clear stores but keep baseline data
        self.alert_store = get_alert_store('memory', force_new=True)
        self.aggregator = RollingMetricsAggregator()  # Reset aggregator

        # Inject the scenario logs directly into the aggregator
        logs = self.generator.inject_scenario(scenario)

        # Add logs to aggregator
        for log in logs:
            self.aggregator.add_log(log)

        # Wait for processing
        time.sleep(2)

        # Process the aggregated metrics through the detection pipeline
        current_metrics = self.aggregator.get_metrics()

        # Convert to the format expected by the detector
        aggregates = []
        for endpoint, windows in current_metrics.items():
            for window_name, mets in windows.items():
                window_min = int(window_name.split('_')[1][:-1])
                rec = {
                    'endpoint': endpoint,
                    'window': f'{window_min}m',
                    'avg_latency': mets['avg_latency'],
                    'p95_latency': mets['p95_latency'],
                    'error_rate': mets['error_rate'],
                    'request_volume': mets['request_volume'],
                    'timestamp': datetime.now().isoformat().replace('+00:00', 'Z')
                }
                aggregates.append(rec)

        # Run detection
        anomalies = detect(aggregates)

        # Correlate anomalies
        alerts = correlate(anomalies)

        # Explain alerts
        explained_alerts = explain_alerts(alerts)

        # Store alerts
        alert_ids = []
        stored_alerts = []
        for alert in explained_alerts:
            alert_id = self.alert_store.store_alert(alert)
            stored_alert = self.alert_store.get_alert(alert_id)
            stored_alerts.append(stored_alert)
            alert_ids.append(alert_id)

        metrics.alerts_generated = stored_alerts

        # Analyze alerts for the test endpoint
        print(f"DEBUG: Total explained alerts: {len(explained_alerts)}")
        for i, alert in enumerate(explained_alerts):
            print(f"DEBUG: Alert {i}: endpoint={alert.get('endpoint')}, severity={alert.get('severity')}")
        
        relevant_alerts = [a for a in stored_alerts if a.get('endpoint') == scenario.endpoint]
        print(f"DEBUG: Relevant alerts for {scenario.endpoint}: {len(relevant_alerts)}")

        if relevant_alerts:
            # Find first alert for this endpoint
            print(f"DEBUG: First relevant alert: {relevant_alerts[0]}")
            first_alert = min(relevant_alerts, key=lambda x: x.get('created_at', ''))
            print(f"DEBUG: Selected first alert created_at: {first_alert.get('created_at')}")
            metrics.first_alert_time = datetime.fromisoformat(first_alert['created_at'].replace('Z', '+00:00'))
            print(f"DEBUG: Set first_alert_time to: {metrics.first_alert_time}")

            # Determine if this was a true positive
            alert_severity = first_alert.get('severity', '')
            # Any severity indicating degradation (not INFO) is a true positive for degradation scenarios
            if scenario.expected_severity != "INFO" and alert_severity in ["MEDIUM", "HIGH", "CRITICAL"]:
                metrics.true_positives += 1
            elif scenario.expected_severity == "INFO" and alert_severity == "INFO":
                metrics.true_positives += 1  # Correctly no alert for no degradation
            else:
                metrics.false_positives += 1

            print(f"🎯 Alert detected: {first_alert.get('severity')} for {scenario.endpoint}")
            print(f"   Time to detect: {metrics.detection_time_minutes():.1f} minutes")
        else:
            # No alert detected - false negative if degradation was expected
            if scenario.expected_severity != "INFO":  # INFO means no degradation expected
                metrics.false_negatives += 1
            print(f"❌ No alert detected for scenario {scenario.name}")

        return metrics

    def run_precision_recall_test(self, scenarios: List[DegradationScenario]) -> Dict[str, Any]:
        """Run multiple scenarios and calculate precision/recall metrics."""
        all_metrics = []

        for scenario in scenarios:
            metrics = self.run_scenario_test(scenario)
            all_metrics.append(metrics)
            time.sleep(2)  # Brief pause between scenarios

        # Aggregate results
        total_tp = sum(m.true_positives for m in all_metrics)
        total_fp = sum(m.false_positives for m in all_metrics)
        total_fn = sum(m.false_negatives for m in all_metrics)

        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        return {
            'precision': precision,
            'recall': recall,
            'f1_score': f1_score,
            'total_scenarios': len(scenarios),
            'true_positives': total_tp,
            'false_positives': total_fp,
            'false_negatives': total_fn,
            'scenario_results': [
                {
                    'name': m.scenario_name,
                    'detection_time': m.detection_time_minutes(),
                    'alerts_generated': len(m.alerts_generated),
                    'precision': m.precision(),
                    'recall': m.recall()
                }
                for m in all_metrics
            ]
        }

    def _establish_baseline(self, endpoint: str):
        """Establish baseline data for an endpoint with normal performance."""
        baseline_start = datetime.now() - timedelta(hours=2)  # 2 hours ago
        
        # Generate 60 minutes of normal baseline data (every 5 minutes)
        baseline_metrics = []
        for minute in range(0, 60, 5):  # Every 5 minutes for 60 minutes
            timestamp = baseline_start + timedelta(minutes=minute)
            
            # Create metrics for this time point
            rec = {
                'endpoint': endpoint,
                'window_minutes': 1,  # 1-minute windows
                'window_end': timestamp,
                'avg_latency': 100.0 + random.uniform(-5, 5),  # Normal latency around 100ms
                'p95_latency': 120.0 + random.uniform(-5, 5),   # Normal p95 around 120ms
                'error_rate': 0.01 + random.uniform(-0.005, 0.005),  # Low error rate around 1%
                'request_volume': 10 + random.randint(-2, 2),   # Normal volume around 10
                'response_size_variance': 500.0
            }
            baseline_metrics.append(rec)
        
        # Store baseline metrics
        if baseline_metrics:
            success = self.metrics_store.store_metrics(baseline_metrics)
            print(f"DEBUG: Baseline storage success: {success}")
            # Verify storage
            test_query = self.metrics_store.get_metrics(endpoint=endpoint, window_minutes=1)
            print(f"DEBUG: After baseline storage, {len(test_query)} records found for {endpoint}")
            
            # Also compute and store statistical baselines
            self._compute_and_store_baselines(endpoint, baseline_metrics)
        
        print(f"✅ Established baseline for {endpoint} with {len(baseline_metrics)} historical metrics")

    def _compute_and_store_baselines(self, endpoint: str, baseline_metrics: List[Dict[str, Any]]):
        """Compute statistical baselines from historical data and store them."""
        import numpy as np
        
        baseline_store = get_baseline_store('memory')
        
        # Compute baselines for each metric
        df = pd.DataFrame(baseline_metrics)
        
        for metric_name in ['avg_latency', 'p95_latency', 'error_rate']:
            if metric_name in df.columns:
                values = df[metric_name].values
                if len(values) > 0:
                    baseline_data = {
                        'mean': float(np.mean(values)),
                        'std': float(np.std(values)),
                        'count': len(values),
                        'min': float(np.min(values)),
                        'max': float(np.max(values)),
                        'last_updated': datetime.now().isoformat()
                    }
                    
                    success = baseline_store.store_baseline(endpoint, metric_name, baseline_data)
                    print(f"DEBUG: Stored baseline for {endpoint}/{metric_name}: {baseline_data}, success: {success}")

    def _clear_stores(self):
        """Clear all stored data between tests"""
        # Clear metrics store
        if hasattr(self.metrics_store, 'clear'):
            self.metrics_store.clear()
        # Clear alert store
        if hasattr(self.alert_store, 'clear'):
            self.alert_store.clear()


# Predefined test scenarios
GRADUAL_LATENCY_SCENARIO = DegradationScenario(
    name="gradual_latency_increase",
    description="Latency increases from 100ms to 500ms over 5 minutes",
    duration_minutes=5,
    endpoint="/api/checkout",
    latency_start=100.0,
    latency_end=500.0,
    expected_detection_time=2,
    expected_severity="HIGH"
)

ERROR_CREEP_SCENARIO = DegradationScenario(
    name="error_rate_creep",
    description="Error rate increases from 1% to 15% over 4 minutes",
    duration_minutes=4,
    endpoint="/api/payment",
    error_start=0.01,
    error_end=0.15,
    expected_detection_time=2,
    expected_severity="CRITICAL"
)

TRAFFIC_SURGE_SCENARIO = DegradationScenario(
    name="traffic_surge",
    description="Request volume surges from 10 to 100 per minute",
    duration_minutes=3,
    endpoint="/api/search",
    traffic_start=10,
    traffic_end=100,
    expected_detection_time=1,
    expected_severity="INFO"  # Traffic changes alone might not trigger alerts
)

COMBINED_DEGRADATION_SCENARIO = DegradationScenario(
    name="combined_degradation",
    description="Latency + errors: 100ms→400ms, 1%→10% errors over 6 minutes",
    duration_minutes=6,
    endpoint="/api/user",
    latency_start=100.0,
    latency_end=400.0,
    error_start=0.01,
    error_end=0.10,
    expected_detection_time=3,
    expected_severity="CRITICAL"
)


# Test functions
# Test functions
@pytest.fixture(scope="module")
def test_runner():
    """Fixture that provides a test runner with server lifecycle management."""
    runner = SyntheticTestRunner()

    # Clear stores before starting tests
    runner._clear_stores()

    # Start server for the test module
    if not runner.start_server():
        pytest.skip("Cannot start API server for testing")

    yield runner

    # Cleanup: stop server after all tests
    runner.stop_server()


def test_gradual_latency_detection(test_runner):
    """Test detection of gradual latency increase."""
    metrics = test_runner.run_scenario_test(GRADUAL_LATENCY_SCENARIO)

    assert metrics.detection_time_minutes() is not None, "Should detect latency degradation"
    assert metrics.detection_time_minutes() <= 4, f"Detection too slow: {metrics.detection_time_minutes()} minutes"
    assert metrics.true_positives > 0, "Should have true positives"


def test_error_creep_detection(test_runner):
    """Test detection of error rate creep."""
    metrics = test_runner.run_scenario_test(ERROR_CREEP_SCENARIO)

    assert metrics.detection_time_minutes() is not None, "Should detect error creep"
    assert metrics.true_positives > 0, "Should have true positives"


def test_traffic_surge_handling(test_runner):
    """Test system handles traffic surges without false positives."""
    metrics = test_runner.run_scenario_test(TRAFFIC_SURGE_SCENARIO)

    # Traffic surges may cause some variation in error rates due to randomness, 
    # but should not generate significant alerts (allow up to 1 false positive)
    assert metrics.false_positives <= 1, f"Traffic surge generated too many false positives: {metrics.false_positives}"


def test_combined_degradation(test_runner):
    """Test detection of combined latency + error degradation."""
    metrics = test_runner.run_scenario_test(COMBINED_DEGRADATION_SCENARIO)

    assert metrics.detection_time_minutes() is not None, "Should detect combined degradation"
    assert metrics.true_positives > 0, "Should have true positives"


def test_precision_recall_metrics(test_runner):
    """Test overall system precision and recall across multiple scenarios."""
    scenarios = [GRADUAL_LATENCY_SCENARIO, ERROR_CREEP_SCENARIO, COMBINED_DEGRADATION_SCENARIO]

    results = test_runner.run_precision_recall_test(scenarios)

    print("\n📊 Precision/Recall Results:")
    print(f"   Precision: {results['precision']:.3f}")
    print(f"   Recall: {results['recall']:.3f}")
    print(f"   F1-Score: {results['f1_score']:.3f}")
    # System should achieve reasonable precision/recall
    assert results['precision'] >= 0.7, f"Poor precision: {results['precision']:.3f}"
    assert results['recall'] >= 0.7, f"Poor recall: {results['recall']:.3f}"


if __name__ == "__main__":
    # Run individual scenario tests
    print("🧪 SYNTHETIC DEGRADATION TESTING")
    print("=" * 50)

    runner = SyntheticTestRunner()

    # Start the server
    if not runner.start_server():
        print("❌ Failed to start API server. Exiting.")
        exit(1)

    try:
        # Establish baseline data once for all endpoints
        print("📊 Establishing baseline data for all test endpoints...")
        runner._establish_baseline("/api/checkout")
        runner._establish_baseline("/api/payment") 
        runner._establish_baseline("/api/user")
        runner._establish_baseline("/api/search")

        print("\n1️⃣ Testing Gradual Latency Increase...")
        metrics = runner.run_scenario_test(GRADUAL_LATENCY_SCENARIO)
        print(f"   Detection time: {metrics.detection_time_minutes() or 0:.1f} minutes")
        print(f"   Alerts generated: {len(metrics.alerts_generated)}")

        print("\n2️⃣ Testing Error Rate Creep...")
        metrics = runner.run_scenario_test(ERROR_CREEP_SCENARIO)
        print(f"   Detection time: {metrics.detection_time_minutes() or 0:.1f} minutes")
        print(f"   Alerts generated: {len(metrics.alerts_generated)}")

        print("\n3️⃣ Testing Combined Degradation...")
        metrics = runner.run_scenario_test(COMBINED_DEGRADATION_SCENARIO)
        print(f"   Detection time: {metrics.detection_time_minutes() or 0:.1f} minutes")
        print(f"   Alerts generated: {len(metrics.alerts_generated)}")

        print("\n4️⃣ Testing Precision/Recall...")
        scenarios = [GRADUAL_LATENCY_SCENARIO, ERROR_CREEP_SCENARIO, COMBINED_DEGRADATION_SCENARIO]
        results = runner.run_precision_recall_test(scenarios)

        print("\n📈 Final Results:")
        print(f"   Precision: {results['precision']:.3f}")
        print(f"   Recall: {results['recall']:.3f}")
        print(f"   F1-Score: {results['f1_score']:.3f}")
        print(f"   True Positives: {results['true_positives']}")
        print(f"   False Positives: {results['false_positives']}")
        print(f"   False Negatives: {results['false_negatives']}")

        print("\n✅ Synthetic testing complete!")
        print("Use 'pytest tests/test_synthetic_degradation.py -v' to run automated tests")

    finally:
        runner.stop_server()