#!/usr/bin/env python3
"""
Phase 1 Infrastructure Validation Script

Verifies that all Phase 1 infrastructure components are working correctly:
- Docker containers are running
- Prometheus is scraping
- Kafka topics exist
- Databases are accessible
- Models are trained

Usage:
    python scripts/verify_phase1.py [--quick] [--verbose]
"""

import os
import sys
import time
import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


class Phase1Verifier:
    """Verifies Phase 1 infrastructure"""
    
    def __init__(self, quick: bool = False, verbose: bool = False):
        self.quick = quick
        self.verbose = verbose
        self.results: Dict[str, Tuple[bool, str]] = {}
        self.project_root = Path(__file__).resolve().parent.parent
        
    def print_header(self, text: str):
        """Print section header"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.BLUE}{text:^70}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.ENDC}\n")
    
    def print_status(self, name: str, success: bool, msg: str):
        """Print check result"""
        status = f"{Colors.GREEN}✓ PASS{Colors.ENDC}" if success else f"{Colors.RED}✗ FAIL{Colors.ENDC}"
        print(f"  {status} | {name}")
        if self.verbose or not success:
            print(f"       {msg}")
        self.results[name] = (success, msg)
    
    def check_docker_running(self) -> bool:
        """Check if Docker compose services are running"""
        self.print_header("Docker Infrastructure")
        
        expected_services = [
            'zookeeper',
            'kafka',
            'prometheus',
            'timescaledb',
            'postgres',
            'redis',
            'grafana'
        ]
        
        try:
            result = subprocess.run(
                ['docker', 'ps', '--format', '{{.Names}}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            running_services = result.stdout.strip().split('\n')
            
            all_running = all(svc in running_services for svc in expected_services)
            
            if all_running:
                self.print_status(
                    "Docker Services",
                    True,
                    f"All {len(expected_services)} services running"
                )
                return True
            else:
                missing = [svc for svc in expected_services if svc not in running_services]
                self.print_status(
                    "Docker Services",
                    False,
                    f"Missing services: {', '.join(missing)}"
                )
                return False
        except Exception as e:
            self.print_status("Docker Services", False, f"Error: {e}")
            return False
    
    def check_prometheus(self) -> bool:
        """Check Prometheus connectivity and scrape targets"""
        self.print_header("Prometheus Metrics")
        
        try:
            import httpx
            
            client = httpx.Client(timeout=5)
            
            # Check Prometheus API
            response = client.get('http://localhost:9090/api/v1/targets')
            if response.status_code != 200:
                self.print_status("Prometheus API", False, f"HTTP {response.status_code}")
                return False
            
            data = response.json()
            targets = data.get('data', {}).get('activeTargets', [])
            
            self.print_status(
                "Prometheus API",
                True,
                f"Connected, {len(targets)} scrape targets"
            )
            
            # Check if any targets are up
            up_count = sum(1 for t in targets if t.get('health') == 'up')
            self.print_status(
                "Scrape Targets",
                up_count > 0,
                f"{up_count}/{len(targets)} targets healthy"
            )
            
            return up_count > 0
        except Exception as e:
            self.print_status("Prometheus", False, f"Error: {e}")
            return False
    
    def check_kafka(self) -> bool:
        """Check Kafka topic creation and connectivity"""
        self.print_header("Kafka Streaming")
        
        try:
            from kafka import KafkaConsumer
            from kafka.errors import KafkaError
            
            # Check Kafka connectivity
            consumer = KafkaConsumer(
                bootstrap_servers=['localhost:9092'],
                consumer_timeout_ms=1000,
                request_timeout_ms=5000
            )
            
            topics = consumer.topics()
            consumer.close()
            
            expected_topics = {
                'raw-metrics',
                'feature-store',
                'anomalies',
                'alerts',
                'root-causes'
            }
            
            found_topics = expected_topics.intersection(topics)
            
            self.print_status(
                "Kafka Connectivity",
                True,
                f"Connected to Kafka, {len(topics)} topics available"
            )
            
            self.print_status(
                "Kafka Topics",
                len(found_topics) >= 3,
                f"Found {len(found_topics)}/5 expected topics"
            )
            
            return len(found_topics) >= 3
        except Exception as e:
            self.print_status("Kafka", False, f"Error: {e}")
            return False
    
    def check_timescaledb(self) -> bool:
        """Check TimescaleDB schema and tables"""
        self.print_header("TimescaleDB Time-Series")
        
        try:
            import psycopg2
            
            conn = psycopg2.connect(
                host='localhost',
                port=5432,
                user='monitoring',
                password='monitoring_pass_123',
                database='metrics',
                connect_timeout=5
            )
            
            cursor = conn.cursor()
            
            # Check hypertables
            cursor.execute("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public'
                LIMIT 20
            """)
            
            tables = [row[0] for row in cursor.fetchall()]
            expected_tables = {'metrics', 'anomalies', 'alerts', 'baselines'}
            found = expected_tables.intersection(set(tables))
            
            self.print_status(
                "TimescaleDB Connection",
                True,
                f"Connected to metrics database"
            )
            
            self.print_status(
                "TimescaleDB Tables",
                len(found) > 0,
                f"Found {len(found)}/{len(expected_tables)} expected tables: {', '.join(found)}"
            )
            
            cursor.close()
            conn.close()
            
            return len(found) > 0
        except Exception as e:
            self.print_status("TimescaleDB", False, f"Error: {e}")
            return False
    
    def check_postgres(self) -> bool:
        """Check PostgreSQL schema"""
        self.print_header("PostgreSQL Operational Data")
        
        try:
            import psycopg2
            
            conn = psycopg2.connect(
                host='localhost',
                port=5433,
                user='monitoring',
                password='monitoring_pass_123',
                database='alerts',
                connect_timeout=5
            )
            
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public'
                LIMIT 30
            """)
            
            tables = [row[0] for row in cursor.fetchall()]
            expected_tables = {'alerts', 'incidents', 'audit_logs'}
            found = expected_tables.intersection(set(tables))
            
            self.print_status(
                "PostgreSQL Connection",
                True,
                f"Connected to alerts database"
            )
            
            self.print_status(
                "PostgreSQL Tables",
                len(found) > 0,
                f"Found {len(found)}/{len(expected_tables)} expected tables: {', '.join(found)}"
            )
            
            cursor.close()
            conn.close()
            
            return len(found) > 0
        except Exception as e:
            self.print_status("PostgreSQL", False, f"Error: {e}")
            return False
    
    def check_redis(self) -> bool:
        """Check Redis connectivity"""
        self.print_header("Redis Cache")
        
        try:
            import redis
            
            r = redis.Redis(
                host='localhost',
                port=6379,
                socket_connect_timeout=5
            )
            
            r.ping()
            
            self.print_status(
                "Redis Connection",
                True,
                "Redis is online and responding"
            )
            
            return True
        except Exception as e:
            self.print_status("Redis", False, f"Error: {e}")
            return False
    
    def check_models(self) -> bool:
        """Check if trained models exist"""
        self.print_header("Trained Models")
        
        models_dir = self.project_root / 'models'
        
        expected_models = {
            'lstm': models_dir / 'lstm',
            'isolation_forest': models_dir / 'isolation_forest',
            'baselines.json': models_dir / 'baselines.json'
        }
        
        found = [name for name, path in expected_models.items() if path.exists()]
        
        self.print_status(
            "Model Files",
            len(found) >= 1,
            f"Found {len(found)}/{len(expected_models)} model artifacts"
        )
        
        return len(found) >= 1
    
    def check_requirements(self) -> bool:
        """Check if all requirements are installed"""
        self.print_header("Python Dependencies")
        
        critical_packages = [
            'kafka',
            'pydantic',
            'httpx',
            'psycopg2',
            'redis',
            'tensorflow',
            'sklearn',
            'pandas',
            'numpy'
        ]
        
        missing = []
        for pkg in critical_packages:
            try:
                __import__(pkg.replace('-', '_'))
            except ImportError:
                missing.append(pkg)
        
        self.print_status(
            "Critical Packages",
            len(missing) == 0,
            f"Installed: {len(critical_packages) - len(missing)}/{len(critical_packages)}"
        )
        
        return len(missing) == 0
    
    def check_config(self) -> bool:
        """Check if configuration is accessible"""
        self.print_header("Configuration")
        
        try:
            sys.path.insert(0, str(self.project_root))
            from src.config import settings
            
            # Verify critical settings
            checks = [
                settings.KAFKA_BOOTSTRAP_SERVERS != '',
                settings.TIMESCALEDB_URL != '',
                settings.POSTGRES_URL != '',
                settings.REDIS_URL != ''
            ]
            
            self.print_status(
                "Configuration Loading",
                all(checks),
                "All critical settings accessible"
            )
            
            return all(checks)
        except Exception as e:
            self.print_status("Configuration", False, f"Error: {e}")
            return False
    
    def run_all_checks(self) -> bool:
        """Run all validations"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}API Degradation Detection System - Phase 1 Verification{Colors.ENDC}\n")
        
        checks = [
            self.check_requirements,
            self.check_config,
            self.check_docker_running,
            self.check_prometheus,
            self.check_kafka,
            self.check_timescaledb,
            self.check_postgres,
            self.check_redis,
            self.check_models
        ]
        
        for check in checks:
            if not self.quick:
                time.sleep(0.3)  # Brief pause between checks
            try:
                check()
            except Exception as e:
                log.error(f"Check {check.__name__} failed: {e}")
        
        # Summary
        self.print_header("Verification Summary")
        
        passed = sum(1 for success, _ in self.results.values() if success)
        total = len(self.results)
        
        print(f"{Colors.BOLD}Results: {passed}/{total} checks passed{Colors.ENDC}\n")
        
        if passed == total:
            print(f"{Colors.GREEN}{Colors.BOLD}✓ Phase 1 infrastructure fully operational!{Colors.ENDC}")
            print(f"\n{Colors.BOLD}Next Steps:{Colors.ENDC}")
            print("1. Start Prometheus collector:")
            print("   python src/ingestion/prometheus_collector.py")
            print("\n2. Start feature extraction service:")
            print("   python src/feature_engineering/feature_extractor.py")
            print("\n3. Begin Phase 2: Anomaly Detection Ensemble")
            return True
        else:
            print(f"{Colors.YELLOW}{Colors.BOLD}⚠ Some components need attention:{Colors.ENDC}")
            for name, (success, msg) in self.results.items():
                if not success:
                    print(f"  - {name}: {msg}")
            return False


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Phase 1 Infrastructure Verification'
    )
    parser.add_argument('--quick', action='store_true', help='Skip delays between checks')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    verifier = Phase1Verifier(quick=args.quick, verbose=args.verbose)
    success = verifier.run_all_checks()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
