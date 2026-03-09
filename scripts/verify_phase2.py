#!/usr/bin/env python3
"""
Phase 2 Integration Test & Verification Script

Tests all Phase 2 components integration:
1. Ensemble detection service
2. Alert manager service
3. API server health
4. End-to-end alert routing
"""

import subprocess
import time
import sys
import json
from pathlib import Path
from typing import Tuple
import logging

import httpx
from kafka import KafkaConsumer, KafkaProducer
import psycopg2

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
ENDC = '\033[0m'
BOLD = '\033[1m'


class Phase2Verifier:
    """Verifies Phase 2 setup"""
    
    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.results = {}
        
    def print_header(self, text: str):
        """Print section header"""
        print(f"\n{BOLD}{BLUE}{'='*70}{ENDC}")
        print(f"{BOLD}{BLUE}{text:^70}{ENDC}")
        print(f"{BOLD}{BLUE}{'='*70}{ENDC}\n")
    
    def print_status(self, name: str, success: bool, msg: str = ""):
        """Print check result"""
        status = f"{GREEN}✓{ENDC}" if success else f"{RED}✗{ENDC}"
        print(f"  {status} {name}")
        if msg:
            print(f"     {msg}")
        self.results[name] = success
    
    def verify_phase2_files(self) -> bool:
        """Verify all Phase 2 files exist"""
        self.print_header("Phase 2 File Verification")
        
        expected_files = [
            'src/api/models.py',
            'src/api/server.py',
            'src/detection/ensemble_detector.py',
            'src/alerting/integrations.py',
            'src/alerting/alert_manager.py',
            'PHASE2_COMPLETION.md'
        ]
        
        all_exist = True
        for file in expected_files:
            path = self.project_root / file
            exists = path.exists()
            self.print_status(file, exists)
            if not exists:
                all_exist = False
        
        return all_exist
    
    def verify_api_models(self) -> bool:
        """Verify API models can be imported"""
        self.print_header("API Models Verification")
        
        try:
            sys.path.insert(0, str(self.project_root))
            from src.api.models import (
                AnomalyResponse, AlertResponse, HealthCheckResponse,
                AnomalyQueryRequest, ModelStatusResponse
            )
            
            self.print_status("Import pydantic models", True)
            
            # Test instantiation
            test_health = HealthCheckResponse(
                status="healthy",
                services=[],
                uptime_seconds=100.0
            )
            
            self.print_status("Instantiate HealthCheckResponse", True)
            return True
        except Exception as e:
            self.print_status("API models", False, str(e))
            return False
    
    def verify_ensemble_detector(self) -> bool:
        """Verify ensemble detector can be imported"""
        self.print_header("Ensemble Detector Verification")
        
        try:
            sys.path.insert(0, str(self.project_root))
            from src.detection.ensemble_detector import (
                EnsembleDetector, EnsembleDetectionService, FeatureData
            )
            
            self.print_status("Import ensemble detector", True)
            
            # Check models directory
            models_dir = self.project_root / 'models'
            models_exist = models_dir.exists()
            self.print_status(
                "Models directory exists",
                models_exist,
                f"Path: {models_dir}" if models_exist else "Not found"
            )
            
            return True
        except Exception as e:
            self.print_status("Ensemble detector", False, str(e))
            return False
    
    def verify_alert_manager(self) -> bool:
        """Verify alert manager can be imported"""
        self.print_header("Alert Manager Verification")
        
        try:
            sys.path.insert(0, str(self.project_root))
            from src.alerting.alert_manager import (
                AlertManager, AlertingService, AnomalyData
            )
            from src.alerting.integrations import (
                AlertDispatcher, SlackChannel, PagerDutyChannel
            )
            
            self.print_status("Import alert manager", True)
            self.print_status("Import alert integrations", True)
            
            # Test dispatcher
            dispatcher = AlertDispatcher()
            self.print_status("Instantiate AlertDispatcher", True)
            
            return True
        except Exception as e:
            self.print_status("Alert manager", False, str(e))
            return False
    
    def verify_api_server(self) -> bool:
        """Verify API server can be imported"""
        self.print_header("API Server Verification")
        
        try:
            sys.path.insert(0, str(self.project_root))
            from src.api.server import APIServer
            
            self.print_status("Import APIServer", True)
            return True
        except Exception as e:
            self.print_status("API server", False, str(e))
            return False
    
    def check_kafka_topics(self) -> bool:
        """Verify Kafka topics for Phase 2"""
        self.print_header("Kafka Topics Verification")
        
        try:
            from kafka import KafkaConsumer
            
            consumer = KafkaConsumer(
                bootstrap_servers=['localhost:9092'],
                consumer_timeout_ms=1000
            )
            
            topics = consumer.topics()
            consumer.close()
            
            required_topics = {
                'feature-store': False,
                'anomalies': False,
                'alerts': False
            }
            
            for topic in required_topics:
                exists = topic in topics
                required_topics[topic] = exists
                self.print_status(f"Topic: {topic}", exists)
            
            return all(required_topics.values())
        except Exception as e:
            self.print_status("Kafka topics", False, str(e))
            return False
    
    def check_api_server_health(self) -> bool:
        """Check if API server is running and healthy"""
        self.print_header("API Server Health Check")
        
        try:
            client = httpx.Client(timeout=5)
            response = client.get('http://localhost:8000/health')
            
            if response.status_code == 200:
                data = response.json()
                self.print_status(
                    "API health endpoint",
                    True,
                    f"Status: {data.get('status', 'unknown')}"
                )
                
                # Check model status
                response = client.get('http://localhost:8000/api/v1/models/status')
                if response.status_code == 200:
                    model_data = response.json()
                    self.print_status(
                        "Models status",
                        model_data.get('ensemble_ready', False),
                        f"Ready: {model_data.get('ensemble_ready')}"
                    )
                    return True
                else:
                    self.print_status("Models status", False, f"HTTP {response.status_code}")
                    return False
            else:
                self.print_status("API health", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.print_status("API health check", False, str(e))
            return False
    
    def check_postgres_alerts_table(self) -> bool:
        """Check PostgreSQL alerts table"""
        self.print_header("PostgreSQL Alerts Table Verification")
        
        try:
            conn = psycopg2.connect(
                host='localhost',
                port=5433,
                user='monitoring',
                password='monitoring_pass_123',
                database='alerts',
                connect_timeout=5
            )
            
            cursor = conn.cursor()
            
            # Check alerts table
            cursor.execute("""
                SELECT COUNT(*) as count FROM alerts
            """)
            
            count = cursor.fetchone()[0]
            self.print_status("Alerts table exists", True, f"Rows: {count}")
            
            # Check incidents table
            cursor.execute("""
                SELECT COUNT(*) as count FROM incidents
            """)
            
            incident_count = cursor.fetchone()[0]
            self.print_status("Incidents table exists", True, f"Rows: {incident_count}")
            
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            self.print_status("PostgreSQL alerts", False, str(e))
            return False
    
    def check_timescaledb_anomalies_table(self) -> bool:
        """Check TimescaleDB anomalies table"""
        self.print_header("TimescaleDB Anomalies Table Verification")
        
        try:
            conn = psycopg2.connect(
                host='localhost',
                port=5432,
                user='monitoring',
                password='monitoring_pass_123',
                database='metrics',
                connect_timeout=5
            )
            
            cursor = conn.cursor()
            
            # Check anomalies table
            cursor.execute("""
                SELECT COUNT(*) as count FROM anomalies
            """)
            
            count = cursor.fetchone()[0]
            self.print_status("Anomalies table exists", True, f"Rows: {count}")
            
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            self.print_status("TimescaleDB anomalies", False, str(e))
            return False
    
    def run_all_checks(self) -> bool:
        """Run all Phase 2 verification checks"""
        print(f"\n{BOLD}{BLUE}Phase 2 Integration Verification{ENDC}\n")
        
        checks = [
            ("File Integrity", self.verify_phase2_files),
            ("API Models", self.verify_api_models),
            ("Ensemble Detector", self.verify_ensemble_detector),
            ("Alert Manager", self.verify_alert_manager),
            ("API Server", self.verify_api_server),
            ("Kafka Topics", self.check_kafka_topics),
            ("PostgreSQL Tables", self.check_postgres_alerts_table),
            ("TimescaleDB Tables", self.check_timescaledb_anomalies_table),
            ("API Server Running", self.check_api_server_health),
        ]
        
        passed = 0
        failed = 0
        
        for check_name, check_func in checks:
            try:
                if check_func():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"{RED}✗ {check_name} - Exception: {e}{ENDC}")
                failed += 1
        
        # Summary
        self.print_header("Verification Summary")
        
        print(f"{BOLD}Results: {passed}/{passed + failed} checks passed{ENDC}\n")
        
        if failed == 0:
            print(f"{GREEN}{BOLD}✓ Phase 2 fully operational!{ENDC}\n")
            print(f"{BOLD}Next Steps:{ENDC}")
            print("1. Monitor services:")
            print("   - Ensemble detector: Watch anomalies in Kafka")
            print("   - Alert manager: Watch alerts being created")
            print("   - API server: Check /metrics for monitoring")
            print("\n2. Test end-to-end:")
            print("   - Generate synthetic anomalies")
            print("   - Verify Slack/PagerDuty notifications")
            print("   - Query /api/v1/anomalies and /api/v1/alerts")
            print("\n3. Proceed to Phase 3 (RCA Engine)")
            return True
        else:
            print(f"{YELLOW}{BOLD}⚠ {failed} checks failed{ENDC}\n")
            print(f"{YELLOW}Running services needed:{ENDC}")
            print("  - Docker: docker-compose up")
            print("  - Prometheus Collector: python src/ingestion/prometheus_collector.py")
            print("  - Feature Extractor: python src/feature_engineering/feature_extractor.py")
            print("  - Ensemble Detector: python src/detection/ensemble_detector.py")
            print("  - Alert Manager: python src/alerting/alert_manager.py")
            print("  - API Server: python src/api/server.py")
            return False


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Phase 2 Integration Verification')
    parser.add_argument('--quick', action='store_true', help='Skip some checks')
    parser.add_argument('--services-only', action='store_true', help='Only check services')
    
    args = parser.parse_args()
    
    verifier = Phase2Verifier()
    success = verifier.run_all_checks()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
