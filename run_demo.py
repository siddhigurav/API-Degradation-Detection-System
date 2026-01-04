"""
Demo Script: Complete EWS Failure Injection and Detection Workflow

This script demonstrates the full EWS system:
1. Start the API service
2. Run failure injection simulation
3. Run anomaly detection
4. Show results
"""

import subprocess
import time
import sys
import os

# ...existing code...

from src.failure_injector import FailureInjector

def run_command(cmd, cwd=None, shell=False):
    """Run a command and return success status."""
    try:
        result = subprocess.run(cmd, shell=shell, cwd=cwd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def main():
    print("🚀 EWS Demo: Failure Injection & Detection")
    print("=" * 50)

    # Step 1: Start the API service
    print("📡 Step 1: Starting API service...")
    success, stdout, stderr = run_command([sys.executable, "src/ingest_service.py"])
    if not success:
        print(f"❌ Failed to start API service: {stderr}")
        return

    # Wait for service to start
    time.sleep(3)
    print("✅ API service started")

    # Step 2: Run failure injection
    print("\n💥 Step 2: Running failure injection simulation...")
    print("   This will simulate: Normal → Latency Degradation → Error Spikes → Recovery")

    # Import and run the injector
    try:
        # Removed duplicate sys.path.append and import since it's now at the top
        injector = FailureInjector()
        print("   📊 Running 3-minute simulation...")
        injector.run_simulation(duration_minutes=3)

    except Exception as e:
        print(f"❌ Failure injection failed: {e}")
        return
