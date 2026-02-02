#!/usr/bin/env python3
"""
Failure Injection Demo Script

This script demonstrates the failure injection system by:
1. Starting with normal traffic
2. Gradually increasing latency
3. Introducing error spikes
4. Sending all logs to the /ingest API

Run this to see the system in action with realistic failure patterns.
"""

import time
import subprocess
import sys
import os

def check_api_health():
    """Check if the ingest API is running."""
    try:
        import httpx
        response = httpx.get("http://localhost:8001/health", timeout=5)
        return response.status_code == 200
    except:
        return False

def start_ingest_service():
    """Start the ingest service if not running."""
    print("🔄 Checking if ingest service is running...")

    if check_api_health():
        print("✅ Ingest service is already running")
        return True

    print("🚀 Starting ingest service...")
    try:
        # Start the ingest service in background
        process = subprocess.Popen([
            sys.executable, "src/ingest_service.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Wait for it to start
        time.sleep(3)

        if check_api_health():
            print("✅ Ingest service started successfully")
            return True
        else:
            print("❌ Failed to start ingest service")
            return False

    except Exception as e:
        print(f"❌ Error starting ingest service: {e}")
        return False

def run_failure_injection():
    """Run the failure injection simulation."""
    print("\n" + "="*60)
    print("🔥 FAILURE INJECTION DEMO")
    print("="*60)
    print("This demo will simulate realistic API degradation:")
    print("• 1 min: Normal traffic (baseline performance)")
    print("• 2 min: Gradual latency increase (1x → 3x)")
    print("• 1 min: Error spike (10% error rate)")
    print("• 1 min: Recovery (back to normal)")
    print("="*60)

    try:
        # Run the failure injector
        result = subprocess.run([
            sys.executable, "src/failure_injector.py",
            "--duration", "5",  # 5 minute demo
            "--url", "http://localhost:8001"
        ], check=True)

        print("\n✅ Failure injection completed!")
        print("💡 Next: Run 'python src/process_once.py' to analyze the failures")
        print("📊 Or run 'python run_demo.py' to see the full detection pipeline")

    except subprocess.CalledProcessError as e:
        print(f"❌ Failure injection failed: {e}")
        return False
    except KeyboardInterrupt:
        print("\n🛑 Demo interrupted by user")
        return False

    return True

def main():
    print("🎭 API Degradation Detection - Failure Injection Demo")
    print("="*55)

    # Check if we're in the right directory
    if not os.path.exists("src/failure_injector.py"):
        print("❌ Error: src/failure_injector.py not found")
        print("💡 Make sure you're running from the project root directory")
        return

    # Start ingest service
    if not start_ingest_service():
        print("❌ Cannot proceed without ingest service")
        return

    # Clear any existing data
    print("\n🧹 Clearing existing data...")
    data_dir = "data"
    for file in ["raw_logs.jsonl", "aggregates.jsonl", "alerts.jsonl"]:
        filepath = os.path.join(data_dir, file)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f"   Cleared {file}")
            except:
                pass

    # Run the demo
    success = run_failure_injection()

    if success:
        print("\n" + "="*60)
        print("🔍 ANALYZING INJECTED FAILURES")
        print("="*60)

        # Run analysis
        try:
            result = subprocess.run([
                sys.executable, "run_demo.py"
            ], check=True, capture_output=True, text=True)

            # Extract just the key results
            lines = result.stdout.split('\n')
            for line in lines:
                if 'Found' in line and 'alerts' in line:
                    print(f"📊 {line.strip()}")
                elif 'Generated' in line and 'alert candidates' in line:
                    print(f"🔗 {line.strip()}")
                elif 'Stored' in line and 'alerts' in line:
                    print(f"💾 {line.strip()}")

        except subprocess.CalledProcessError as e:
            print(f"❌ Analysis failed: {e}")

        print("\n🎉 Demo completed successfully!")
        print("📈 Check the logs in data/raw_logs.jsonl")
        print("🚀 Run full demo: python run_demo.py")
        print("🌐 Start API server: python run_api.py")

if __name__ == "__main__":
    main()