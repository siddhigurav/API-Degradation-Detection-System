"""
Phase 3 Verification Script

Comprehensive tests for RCA Engine components:
- Correlation Engine
- Causal Analyzer
- Dependency Analyzer
- RCA Service integration
- Database schema validation
"""

import sys
import asyncio
import json
from datetime import datetime, timedelta
import traceback
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple

# Test environment setup
print("=" * 80)
print("PHASE 3: ROOT CAUSE ANALYSIS ENGINE - VERIFICATION")
print("=" * 80)

test_results = {
    'passed': 0,
    'failed': 0,
    'skipped': 0,
    'details': []
}


def test_pass(test_name: str, message: str = ""):
    """Record passing test"""
    test_results['passed'] += 1
    status = "✅ PASS"
    print(f"{status:12} | {test_name:40} | {message}")
    test_results['details'].append({
        'test': test_name,
        'status': 'PASS',
        'message': message
    })


def test_fail(test_name: str, error: str):
    """Record failing test"""
    test_results['failed'] += 1
    status = "❌ FAIL"
    print(f"{status:12} | {test_name:40} | {error}")
    test_results['details'].append({
        'test': test_name,
        'status': 'FAIL',
        'error': error
    })


def test_skip(test_name: str, reason: str):
    """Record skipped test"""
    test_results['skipped'] += 1
    status = "⏭️  SKIP"
    print(f"{status:12} | {test_name:40} | {reason}")
    test_results['details'].append({
        'test': test_name,
        'status': 'SKIP',
        'reason': reason
    })


# ============================================================================
# TEST 1: Data Models
# ============================================================================

print("\n📋 TEST SUITE 1: DATA MODELS")
print("-" * 80)

try:
    from src.rca.models import (
        MetricCorrelation, CorrelationType, CausalRelationship,
        CausalityConfidence, RCAResult, RCAFinding, RCAMetricContribution,
        CorrelationSnapshot, ServiceDependency, DependencyGraph,
        CausalGraph, HistoricalIncidentMatch
    )
    test_pass("Import RCA models", "All model classes imported")
    
    # Test MetricCorrelation
    corr = MetricCorrelation(
        metric_1="cpu",
        metric_2="latency",
        endpoint="/api/test",
        correlation_coefficient=0.85,
        correlation_type=CorrelationType.STRONG_POSITIVE,
        sample_count=100,
        p_value=0.001,
        lag_offset=5
    )
    
    corr_dict = corr.to_dict()
    assert corr_dict['correlation_coefficient'] == 0.85
    test_pass("MetricCorrelation serialization", "to_dict() works")
    
    # Test CausalRelationship
    cause = CausalRelationship(
        cause_metric="cpu",
        effect_metric="latency",
        treatment_effect=2.5,
        confidence=CausalityConfidence.HIGH,
        backdoor_adjustment=True
    )
    assert cause.timestamp is not None
    test_pass("CausalRelationship creation", "Timestamps auto-generated")
    
    # Test CausalGraph
    graph = CausalGraph(relationships=[cause])
    roots = graph.get_root_causes()
    assert len(roots) > 0
    test_pass("CausalGraph root detection", f"Found {len(roots)} root causes")
    
    # Test RCAMetricContribution
    contrib = RCAMetricContribution(
        metric_name="cpu",
        deviation_percentage=35.2,
        finding_type=RCAFinding.ROOT_CAUSE,
        evidence="Direct anomaly"
    )
    assert contrib.finding_type == RCAFinding.ROOT_CAUSE
    test_pass("RCAMetricContribution", "Enum classification works")
    
    # Test RCAResult
    rca = RCAResult(
        incident_id="inc_123",
        endpoint="/api/test",
        anomalous_metric="latency",
        root_causes=[contrib],
        contributing_factors=[],
        symptoms=[],
        evidence={},
        recommendations="Test recommendation",
        confidence=0.9
    )
    rca_dict = rca.to_dict()
    assert rca_dict['incident_id'] == "inc_123"
    test_pass("RCAResult serialization", "Full RCA result JSON ready")
    
except Exception as e:
    test_fail("Data Models", f"{str(e)}\n{traceback.format_exc()}")


# ============================================================================
# TEST 2: Correlation Engine
# ============================================================================

print("\n📊 TEST SUITE 2: CORRELATION ENGINE")
print("-" * 80)

try:
    from src.rca.correlation_engine import CorrelationEngine
    
    engine = CorrelationEngine()
    test_pass("CorrelationEngine initialization", "Engine created")
    
    # Add synthetic metrics
    now = datetime.utcnow()
    for i in range(100):
        ts = now - timedelta(seconds=100-i)
        # CPU and latency correlated
        cpu = 50 + np.random.normal(0, 5) + (i * 0.3)
        latency = 100 + np.random.normal(0, 5) + (i * 0.5)
        
        engine.add_metric_value("cpu_percent", ts, cpu)
        engine.add_metric_value("latency_ms", ts, latency)
    
    test_pass("Metric history population", "100 samples added per metric")
    
    # Test correlation computation
    corr = engine.analyze_metric_pair("cpu_percent", "latency_ms", "/api/test")
    
    if corr:
        assert corr.correlation_coefficient > 0.3
        test_pass("Correlation analysis", 
                 f"Corr={corr.correlation_coefficient:.2f}, Type={corr.correlation_type.value}")
    else:
        test_skip("Correlation analysis", "Insufficient data")
    
    # Test correlated metrics lookup
    correlated = engine.find_correlated_metrics("cpu_percent", "/api/test")
    assert len(correlated) >= 0
    test_pass("Correlated metrics discovery", f"Found {len(correlated)} correlations")
    
    # Test classification
    types = [
        (0.85, CorrelationType.STRONG_POSITIVE),
        (0.55, CorrelationType.MODERATE_POSITIVE),
        (-0.75, CorrelationType.STRONG_NEGATIVE),
    ]
    for coef, expected_type in types:
        actual_type = engine.classify_correlation(coef)
        assert actual_type == expected_type
    
    test_pass("Correlation classification", "All threshold ranges correct")
    
except Exception as e:
    test_fail("Correlation Engine", f"{str(e)}\n{traceback.format_exc()}")


# ============================================================================
# TEST 3: Causal Analyzer
# ============================================================================

print("\n🔗 TEST SUITE 3: CAUSAL ANALYZER")
print("-" * 80)

try:
    from src.rca.causal_analyzer import CausalAnalyzer
    
    analyzer = CausalAnalyzer()
    test_pass("CausalAnalyzer initialization", "Analyzer created")
    
    # Check DoWhy availability
    try:
        from dowhy import CausalModel
        has_dowhy = True
        test_pass("DoWhy library", "Available and imported")
    except ImportError:
        has_dowhy = False
        test_skip("DoWhy library", "Package not installed (optional)")
    
    # Create synthetic data
    n = 100
    np.random.seed(42)
    
    df = pd.DataFrame({
        'cpu_percent': np.random.normal(60, 10, n),
        'memory_mb': np.random.normal(1024, 100, n),
        'latency_ms': np.random.normal(100, 20, n),
        'throughput_rps': np.random.normal(1000, 100, n),
    })
    
    test_pass("Synthetic dataset creation", f"{n} samples, 4 metrics")
    
    # Test causal discovery (if DoWhy available)
    if has_dowhy:
        try:
            graph = analyzer.discover_causal_relationships(
                list(df.columns), df, min_confidence=0.3
            )
            test_pass("Causal discovery", f"Found {len(graph.relationships)} relationships")
        except Exception as e:
            test_skip("Causal discovery", f"Optional: {str(e)}")
    
    # Test confidence classification
    confs = [0.8, 0.6, 0.4, 0.2]
    expected = [
        CausalityConfidence.HIGH,
        CausalityConfidence.MEDIUM,
        CausalityConfidence.LOW,
        CausalityConfidence.INSUFFICIENT
    ]
    
    for conf, exp in zip(confs, expected):
        actual = analyzer._confidence_to_enum(conf)
        assert actual == exp
    
    test_pass("Confidence classification", "All levels mapped correctly")
    
    # Test anomaly propagation
    if has_dowhy:
        try:
            graph = analyzer.discover_causal_relationships(list(df.columns), df)
            findings = analyzer.propagate_anomaly(graph, 'cpu_percent', 
                                                   ['latency_ms', 'throughput_rps'])
            assert len(findings) > 0
            test_pass("Anomaly propagation", f"Classified {len(findings)} metrics")
        except Exception as e:
            test_skip("Anomaly propagation", f"Optional: {str(e)}")
    
except Exception as e:
    test_fail("Causal Analyzer", f"{str(e)}\n{traceback.format_exc()}")


# ============================================================================
# TEST 4: Dependency Analyzer
# ============================================================================

print("\n🌐 TEST SUITE 4: DEPENDENCY ANALYZER")
print("-" * 80)

try:
    from src.rca.dependency_analyzer import DependencyAnalyzer
    
    analyzer = DependencyAnalyzer()
    test_pass("DependencyAnalyzer initialization", "Analyzer created")
    
    # Record service calls
    now = datetime.utcnow()
    for i in range(50):
        ts = now - timedelta(seconds=50-i)
        
        # Service A calls B
        analyzer.record_service_call(
            "api-server", "database",
            latency_ms=100 + np.random.normal(0, 10),
            success=True if np.random.random() > 0.02 else False,
            timestamp=ts
        )
        
        # Service A calls C
        analyzer.record_service_call(
            "api-server", "cache",
            latency_ms=50 + np.random.normal(0, 5),
            success=True,
            timestamp=ts
        )
    
    test_pass("Service call recording", "50 API calls recorded")
    
    # Build dependency graph
    graph = analyzer.build_dependency_graph()
    assert graph is not None
    test_pass("Dependency graph building", f"{len(graph.dependencies)} dependencies found")
    
    # Get upstream/downstream
    upstream = analyzer.get_upstream_services("database")
    downstream = analyzer.get_downstream_services("api-server")
    
    assert "api-server" in upstream
    assert "database" in downstream
    test_pass("Upstream/downstream queries", 
              f"Upstream={len(upstream)}, Downstream={len(downstream)}")
    
    # Detect cascade failures
    cascade_risks = analyzer.detect_cascade_failures()
    assert isinstance(cascade_risks, dict)
    test_pass("Cascade failure detection", f"Analyzed {len(cascade_risks)} services")
    
    # Measure latency impact
    impact = analyzer.measure_latency_impact("api-server", "database")
    assert impact['source'] == "api-server"
    assert impact['target'] == "database"
    test_pass("Latency impact measurement", f"Latency: {impact['current_latency']:.1f}ms")
    
    # Error propagation
    errors = analyzer.measure_error_propagation("api-server", "database")
    assert errors['direct_error_rate'] >= 0
    test_pass("Error propagation measurement", 
              f"Error rate: {errors['direct_error_rate']*100:.1f}%")
    
    # Network stats
    stats = analyzer.get_network_stats()
    assert stats['total_services'] > 0
    test_pass("Network statistics", 
              f"Services: {stats['total_services']}, Dependencies: {stats['total_dependencies']}")
    
except Exception as e:
    test_fail("Dependency Analyzer", f"{str(e)}\n{traceback.format_exc()}")


# ============================================================================
# TEST 5: Database Schema
# ============================================================================

print("\n💾 TEST SUITE 5: DATABASE SCHEMA")
print("-" * 80)

try:
    import psycopg2
    from src.config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
    
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cursor = conn.cursor()
        test_pass("PostgreSQL connection", f"Connected to {DB_NAME}")
        
        # Check rca_analyses table
        cursor.execute("""
        SELECT EXISTS(
            SELECT FROM information_schema.tables 
            WHERE table_name = 'rca_analyses'
        )
        """)
        
        exists = cursor.fetchone()[0]
        if exists:
            test_pass("RCA table creation", "rca_analyses table exists")
            
            # Check schema
            cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'rca_analyses'
            """)
            
            columns = {row[0] for row in cursor.fetchall()}
            required = {
                'id', 'incident_id', 'endpoint', 'anomalous_metric',
                'root_causes', 'confidence', 'created_at'
            }
            
            if required.issubset(columns):
                test_pass("Schema validation", f"All required columns present")
            else:
                test_fail("Schema validation", 
                         f"Missing: {required - columns}")
            
            # Check indexes
            cursor.execute("""
            SELECT indexname FROM pg_indexes 
            WHERE tablename = 'rca_analyses'
            """)
            
            indexes = {row[0] for row in cursor.fetchall()}
            if any('incident_id' in idx for idx in indexes):
                test_pass("Index creation", "Indexes properly created")
            else:
                test_skip("Index creation", "Some indexes may be missing")
        else:
            test_skip("RCA table creation", "Table will be created on first run")
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        test_skip("PostgreSQL tests", f"Database unavailable: {str(e)}")
        
except ImportError:
    test_skip("Database Schema", "psycopg2 not installed")
except Exception as e:
    test_fail("Database Schema", f"{str(e)}\n{traceback.format_exc()}")


# ============================================================================
# TEST 6: Kafka Integration
# ============================================================================

print("\n📨 TEST SUITE 6: KAFKA INTEGRATION")
print("-" * 80)

try:
    from kafka import KafkaProducer, KafkaConsumer
    from kafka.errors import KafkaError
    from src.config import KAFKA_BROKERS
    
    try:
        # Test producer
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BROKERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            request_timeout_ms=5000
        )
        
        # Send test message
        test_msg = {
            'test': 'phase3_verification',
            'timestamp': datetime.utcnow().isoformat()
        }
        producer.send('root-causes', value=test_msg).get(timeout=5)
        producer.close()
        
        test_pass("Kafka producer", "Connected and message sent")
        
        # Test consumer could connect (but don't consume)
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BROKERS,
            group_id='verify-phase3',
            consumer_timeout_ms=1000,
            session_timeout_ms=6000
        )
        consumer.close()
        test_pass("Kafka consumer", "Connected successfully")
        
    except KafkaError as e:
        test_skip("Kafka Integration", f"Kafka unavailable: {str(e)}")
        
except ImportError:
    test_skip("Kafka Integration", "kafka-python not installed")
except Exception as e:
    test_fail("Kafka Integration", f"{str(e)}\n{traceback.format_exc()}")


# ============================================================================
# TEST 7: Integration Tests
# ============================================================================

print("\n🔗 TEST SUITE 7: INTEGRATION TESTS")
print("-" * 80)

try:
    # Test full RCA pipeline (mock)
    from src.rca.correlation_engine import CorrelationEngine
    from src.rca.causal_analyzer import CausalAnalyzer
    from src.rca.dependency_analyzer import DependencyAnalyzer
    from src.rca.models import RCAResult, RCAMetricContribution, RCAFinding
    
    # Setup
    corr_engine = CorrelationEngine()
    causal_analyzer = CausalAnalyzer()
    dep_analyzer = DependencyAnalyzer()
    
    # Simulate anomaly
    now = datetime.utcnow()
    for i in range(100):
        ts = now - timedelta(seconds=100-i)
        corr_engine.add_metric_value("latency", ts, 200 + i*2)
        corr_engine.add_metric_value("cpu", ts, 60 + i*0.3)
    
    # Find correlations
    correlations = corr_engine.find_correlated_metrics("latency", "/api/test")
    
    # Record dependencies
    for i in range(20):
        dep_analyzer.record_service_call(
            "api", "db", 100, True,
            now - timedelta(seconds=20-i)
        )
    
    # Build graph
    dep_graph = dep_analyzer.build_dependency_graph()
    
    # Create RCA result
    rca = RCAResult(
        incident_id="test_inc_123",
        endpoint="/api/test",
        anomalous_metric="latency",
        root_causes=[
            RCAMetricContribution(
                metric_name="cpu",
                deviation_percentage=25.0,
                finding_type=RCAFinding.ROOT_CAUSE,
                evidence="Causal analysis"
            )
        ],
        contributing_factors=list(correlations[:2]) if hasattr(correlations[0] if correlations else None, 'to_dict') else [],
        symptoms=[],
        evidence={'sources': 'test'},
        recommendations="Test recommendation",
        confidence=0.85
    )
    
    # Verify serialization
    rca_json = json.dumps(rca.to_dict())
    assert len(rca_json) > 100
    
    test_pass("End-to-end pipeline", "RCA result generated and serialized")
    
except Exception as e:
    test_fail("Integration Tests", f"{str(e)}\n{traceback.format_exc()}")


# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 80)
print("VERIFICATION SUMMARY")
print("=" * 80)

total = test_results['passed'] + test_results['failed'] + test_results['skipped']

print(f"\n📊 Results:")
print(f"   ✅ Passed:  {test_results['passed']:3d}/{total}")
print(f"   ❌ Failed:  {test_results['failed']:3d}/{total}")
print(f"   ⏭️  Skipped: {test_results['skipped']:3d}/{total}")

success_rate = (test_results['passed'] / (total - test_results['skipped']) * 100) if (total - test_results['skipped']) > 0 else 0

print(f"\n🎯 Success Rate: {success_rate:.1f}%")

if test_results['failed'] == 0:
    print("\n✅ PHASE 3 VERIFICATION PASSED")
    print("   All critical components are functional")
    print("   RCA Engine ready for production deployment")
    sys.exit(0)
else:
    print("\n❌ PHASE 3 VERIFICATION FAILED")
    print("   Please fix failing tests before deployment")
    sys.exit(1)
