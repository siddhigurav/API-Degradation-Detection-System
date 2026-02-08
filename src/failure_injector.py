"""
Failure Injection Simulator

This script simulates realistic API traffic patterns for the EWS system:
- Normal baseline traffic
- Gradual latency degradation
- Error rate spikes
- Recovery periods

Sends logs to the /ingest API endpoint in real-time.
"""

import time
import random
import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Configuration
API_BASE_URL = "http://localhost:8001"
INGEST_ENDPOINT = f"{API_BASE_URL}/ingest"

# Traffic simulation parameters
ENDPOINTS = ["/checkout", "/api/users", "/api/orders", "/api/products"]
BASE_LATENCY = 120  # ms
BASE_ERROR_RATE = 0.02  # 2%
REQUESTS_PER_SECOND = 2  # baseline load

class FailureInjector:
    def __init__(self):
        self.client = requests.Session()
        self.current_phase = "normal"
        self.phase_start_time = time.time()
        self.latency_multiplier = 1.0
        self.error_rate_multiplier = 1.0

    def generate_log_entry(self, endpoint: str, timestamp: datetime) -> Dict[str, Any]:
        """Generate a single log entry with current failure injection parameters."""

        # Apply current failure injection
        latency = int(BASE_LATENCY * self.latency_multiplier)
        latency += random.randint(-20, 20)  # natural variation

        # Error injection
        is_error = random.random() < (BASE_ERROR_RATE * self.error_rate_multiplier)
        status_code = 500 if is_error else 200
        error_message = "Internal Server Error" if is_error else None

        # Response size variation
        response_size = 900 + random.randint(-100, 200)

        return {
            "timestamp": timestamp.isoformat() + "Z",
            "endpoint": endpoint,
            "status_code": status_code,
            "latency_ms": max(10, latency),  # minimum 10ms
            "response_size": response_size,
            "error_message": error_message,
        }

    def send_log(self, log_entry: Dict[str, Any]) -> bool:
        """Send a log entry to the ingest API."""
        try:
            response = self.client.post(INGEST_ENDPOINT, json=log_entry, timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send log: {e}")
            return False

    def update_failure_conditions(self, elapsed: float):
        """Update failure injection parameters based on simulation phase."""

        if elapsed < 60:  # First minute: Normal traffic
            self.current_phase = "normal"
            self.latency_multiplier = 1.0
            self.error_rate_multiplier = 1.0

        elif elapsed < 180:  # Next 2 minutes: Gradual latency degradation
            self.current_phase = "latency_degradation"
            # Linear increase from 1.0 to 3.0 over 2 minutes
            progress = (elapsed - 60) / 120
            self.latency_multiplier = 1.0 + (progress * 2.0)
            self.error_rate_multiplier = 1.0

        elif elapsed < 240:  # Next minute: Error spike
            self.current_phase = "error_spike"
            self.latency_multiplier = 2.5  # Keep high latency
            self.error_rate_multiplier = 5.0  # 10% error rate

        elif elapsed < 300:  # Next minute: Recovery
            self.current_phase = "recovery"
            # Gradual recovery
            progress = (elapsed - 240) / 60
            self.latency_multiplier = 2.5 - (progress * 1.5)
            self.error_rate_multiplier = 5.0 - (progress * 4.0)

        else:  # Back to normal, repeat cycle
            self.phase_start_time = time.time()
            self.current_phase = "normal"
            self.latency_multiplier = 1.0
            self.error_rate_multiplier = 1.0

    def run_simulation(self, duration_minutes: int = 10):
        """Run the failure injection simulation."""

        print("🚀 Starting Failure Injection Simulator")
        print(f"📊 Target: {API_BASE_URL}")
        print(f"⏱️  Duration: {duration_minutes} minutes")
        print(f"📈 Endpoints: {', '.join(ENDPOINTS)}")
        print("-" * 50)

        start_time = time.time()
        total_requests = 0
        successful_requests = 0

        try:
            while (time.time() - start_time) < (duration_minutes * 60):
                current_time = datetime.utcnow()
                elapsed = time.time() - start_time

                # Update failure conditions
                self.update_failure_conditions(elapsed)

                # Generate and send requests
                requests_this_second = REQUESTS_PER_SECOND + random.randint(-1, 1)
                for _ in range(max(1, requests_this_second)):
                    endpoint = random.choice(ENDPOINTS)
                    log_entry = self.generate_log_entry(endpoint, current_time)

                    if self.send_log(log_entry):
                        successful_requests += 1
                    total_requests += 1

                # Status update every 10 seconds
                if int(elapsed) % 10 == 0 and elapsed > 0:
                    success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0
                    print(f"📊 Phase: {self.current_phase.upper()} | "
                          f"Latency: {self.latency_multiplier:.1f}x | "
                          f"Errors: {self.error_rate_multiplier:.1f}x | "
                          f"Sent: {total_requests} ({success_rate:.1f}% success)")

                # Wait for next second
                time.sleep(1)

        except KeyboardInterrupt:
            print("\n🛑 Simulation stopped by user")

        finally:
            self.client.close()
            print("\n✅ Simulation completed")
            print(f"📈 Total requests sent: {total_requests}")
            print(f"✅ Successful: {successful_requests}")
            print(f"📊 Success rate: {successful_requests/total_requests*100:.1f}%" if total_requests > 0 else "📊 Success rate: N/A")
            print("💡 Run 'python src/process_once.py' to analyze the injected failures")


def send_log(endpoint: str, latency: int, status: int, size: int):
    """Standalone function to send a single log entry."""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "endpoint": endpoint,
        "status_code": status,
        "latency_ms": latency,
        "response_size": size
    }
    
    try:
        response = requests.post(INGEST_ENDPOINT, json=log_entry, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Failed to send log: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Failure Injection Simulator for EWS")
    parser.add_argument("--duration", type=int, default=10,
                       help="Simulation duration in minutes (default: 10)")
    parser.add_argument("--url", type=str, default="http://localhost:8001",
                       help="API base URL (default: http://localhost:8001)")

    args = parser.parse_args()

    # Update global config
    global API_BASE_URL, INGEST_ENDPOINT
    API_BASE_URL = args.url
    INGEST_ENDPOINT = f"{API_BASE_URL}/ingest"

    # Check if API is available
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if resp.status_code != 200:
            print(f"❌ API health check failed: {resp.status_code}")
            return
    except Exception as e:
        print(f"❌ Cannot connect to API: {e}")
        print("💡 Make sure the ingest service is running: python src/ingest_service.py")
        return

    print("✅ API connection successful")

    # Run simulation
    injector = FailureInjector()
    injector.run_simulation(args.duration)

if __name__ == "__main__":
    main()
