# API Degradation Detection System - Quick Reference Guide

## System Architecture at a Glance

```
Services → Prometheus → Kafka → Stream Processing → ML → RCA → Alerts → Dashboard
                                                    ↓       ↓         ↓
                                                  Database Storage  Notifications
```

---

## Key Components Quick Reference

### 1. Metrics Collection Layer
```
Responsible For: Instrumenting all APIs to emit telemetry
Key Metrics:
  - http_request_duration_seconds (histogram)
  - http_requests_total (counter)
  - http_request_errors_total (counter)
  - service_db_latency_seconds (histogram)

Tools:
  - Prometheus exporters (SDK-based)
  - OpenTelemetry collectors (vendor-neutral)
  - Custom exporters (service-specific)

Output: Raw metrics → Kafka topic: raw-metrics
```

### 2. Streaming & Ingestion
```
Responsible For: High-throughput, durable message bus
Technology: Apache Kafka (3+ brokers, replicated)

Topics:
  raw-metrics          (all raw telemetry)
  processed-metrics    (aggregated + windowed)
  anomalies           (detected anomalies)
  incidents           (grouped incidents)
  rca-results         (root cause findings)

Throughput: 100K-1M metrics/second
Retention: 7 days (for replay)
```

### 3. Feature Processing Service
```
Responsible For: Transforming raw metrics → ML features
Technology: Apache Flink / Spark Streaming
Input: raw-metrics topic
Output: processed-metrics topic

Computations:
  1. Windowing (1m, 5m, 15m, 1h buckets)
  2. Aggregation (mean, p95, p99, max, stddev)
  3. Baseline comparison (z-score, MAD)
  4. Drift detection (KL divergence)
  5. Lag features (for LSTM)

Latency: 1-2 minutes
State: ~10GB for 10K endpoints
```

### 4. Anomaly Detection Engine (AI/ML)
```
Responsible For: Detecting deviations from normal
Ensemble Methods:
  ├─ LSTM Autoencoder (30% weight) → temporal patterns
  ├─ Isolation Forest (20% weight) → isolated anomalies
  ├─ Prophet (30% weight) → trend breaks
  └─ Z-Score Baseline (20% weight) → statistical deviations

Scoring:
  Input: processed-metrics
  Output: anomaly_score (0-1)
  Threshold: >0.7 → alert
  Processing: Every 1 minute for all metrics

Performance:
  - Latency: <500ms per metric
  - Throughput: 100K metrics/min
  - False positive rate: <5%
  - Precision: >95%
```

### 5. Root Cause Analysis Engine
```
Responsible For: Identifying what caused the incident
Inputs: anomaly events + traces + dependency graph
Outputs: ranked list of root causes + confidence scores

Methods:
  1. Causal Graphs (DoWhy)
     - Identify statistical causal relationships
     - Account for confounders
     - Score causal impact

  2. Time-Series Correlation
     - Cross-correlation with time lags
     - Granger causality tests
     - Mutual information analysis

  3. Distributed Trace Correlation
     - OpenTelemetry traces
     - Service call chains
     - Identify slowest hops

Results:
  {
    "primary_root_cause": "database_connection_pool_exhausted",
    "confidence": 0.95,
    "contributing_factors": [...],
    "recommendations": [...]
  }

Latency: <30 seconds (p95)
Accuracy: >90% match with ground truth
```

### 6. Alert & Incident Management
```
Responsible For: Deduplicating, correlating, routing alerts
Input: anomalies topic
Output: incidents + notifications

Pipeline:
  Anomaly → Deduplication (10-min window)
          → Correlation (via service dependencies)
          → Incident Creation/Grouping
          → Notification (Slack, PagerDuty, Email)
          → Incident Lifecycle Management

Deduplication:
  Same endpoint + same metric within 10 min = 1 incident
  Can be extended if new anomalies detected

High-Volume Handling:
  1K+ alerts/min → deduplicated to 10-20 incidents
  Reduces alert fatigue by 95%

Notifications:
  CRITICAL: Slack + PagerDuty (immediate)
  WARNING:  Slack + Email digest
  INFO:     Dashboard + daily email
```

### 7. Data Storage Layer
```
Responsible For: Persistent storage + caching

TimescaleDB (Hypertables):
  metrics         - 100s of billions of data points
  anomalies       - All detected anomalies
  incidents       - Incident lifecycle
  alerts          - Individual alerts

PostgreSQL (Standard Tables):
  users           - User accounts + RBAC
  services        - Service definitions
  dependencies    - Service dependency graph
  alert_rules     - Alert configurations
  baselines       - ML model baselines

Redis (Cache + Pub/Sub):
  Current alerts  - Real-time incident state
  Sessions        - User session data
  Pub/Sub         - Real-time notifications to dashboard

Queries:
  Dashboard:      <500ms (p95)
  Aggregation:    <2s (p95)
  Historical:     <10s (p95)
```

### 8. React Dashboard
```
Responsible For: Real-time visualization & incident management

Pages:
  Overview       - System health, alert count, trends
  Endpoints      - Per-endpoint performance metrics
  Incidents      - List, detail view, RCA visualization
  Configuration  - Alert rules, service deps, integrations

Features:
  ✓ Real-time alerts via WebSocket
  ✓ Causal graph visualization (D3.js)
  ✓ Service dependency map
  ✓ Event timeline
  ✓ Alert acknowledgment + notes
  ✓ Historical trend analysis
  ✓ Configuration management

Tech Stack:
  React 18+                        (UI framework)
  TypeScript                        (type safety)
  Axios                            (API client)
  WebSocket                        (real-time)
  D3.js / Vis.js                  (graph visualization)
  Recharts                         (time-series charts)
```

---

## Data Flow Examples

### Example 1: Latency Spike Detection (Real-Time)

```timeline
T+0:00  | Service A serves requests (baseline: 100ms avg)
        | Prometheus scraper collects metrics every 15s

T+0:15  | Metrics arrive at Kafka raw-metrics topic
        
T+1:00  | Feature Processing Service:
        | - Computed 1-min window: avg_latency = 500ms
        | - Compare vs baseline: (500-100)/50 = 8.0 z-score
        | - Publish to processed-metrics

T+1:05  | Anomaly Detection Engine:
        | - LSTM detects pattern anomaly (score: 0.85)
        | - IF detects spike (score: 0.92)
        | - Prophet detects trend break (score: 0.88)
        | - Ensemble: (0.3×0.85 + 0.2×0.92 + 0.3×0.88 + 0.2×0.90) = 0.88
        | - 0.88 > 0.70 threshold → Publish to anomalies

T+1:10  | RCA Engine:
        | - Get traces for slow requests
        | - Find: Service A → Database latency = 400ms
        | - Correlation: DB latency spike BEFORE Service A slowdown
        | - Root cause: "Database connection pool near limit"
        | - Confidence: 0.95
        | - Publish to incidents topic

T+1:15  | Alert Manager:
        | - Received incident
        | - Check dedup: No similar incident in last 10 min
        | - Create incident #123
        | - Route notification: Slack #alerts + PagerDuty escalation

T+1:16  | Dashboard:
        | - WebSocket push: new incident
        | - Display: Service A latency spike, RC = Database pool
        | - Show: Recommendation = "Increase pool from 50→100"

T+1:20  | Engineer views incident:
        | - Clicks "Auto-Remediate"
        | - System increases DB pool to 100 connections
        | - Monitors metric recovery

T+1:45  | Recovery:
        | - Service A latency returns to 100ms baseline
        | - Anomaly detection: back to normal
        | - Incident auto-resolved
        | - Post-mortem: "Add automated connection pool monitoring"
```

### Example 2: Error Rate Spike (Cascading Failure)

```timeline
T+0:00  | Payment Service error rate: 0.1% (baseline)

T+0:15  | External payment processor becomes slow
        | Payment Service calls timeout (30-second timeout)
        | Error rate jumps to 15%

T+0:20  | Full picture detected:
        | - Direct anomaly: Payment Service error rate
        | - Upstream cause: Payment Processor latency
        | - Correlation analysis finds 20-second time lag
        | - RCA: External payment processor timeout
        | - Confidence: 0.92

T+0:25  | Incident created: "Payment Service Error Spike"
        | Recommended action: "Implement circuit breaker"
        | Notification: CRITICAL severity

T+0:30  | On-call engineer gets PagerDuty alert
        | Views dashboard, sees RCA visualization
        | Decides to fallback to cached payment approval mode

T+0:35  | Error rate returns to baseline
        | Incident resolved
        | Future: Add payment processor health check
```

---

## Scalability Guidelines

### Data Volume Scaling

```
Small: 100 endpoints, 1K metrics/min
├─ Single Kafka broker (OK)
├─ Single Flink TaskManager (OK)
├─ Single TimescaleDB node (OK)
└─ Single FastAPI instance (OK)

Medium: 1K endpoints, 10K metrics/min
├─ 3+ Kafka brokers (recommended)
├─ 3-5 Flink TaskManagers
├─ 2 TimescaleDB nodes (primary + replica)
└─ 3-5 FastAPI instances (load balanced)

Large: 10K+ endpoints, 100K+ metrics/min
├─ 5-10 Kafka brokers (with replication)
├─ 10-20 Flink TaskManagers (distributed processing)
├─ TimescaleDB cluster with Citus (distributed)
└─ 10-20 FastAPI instances (auto-scaling)

Enterprise: 100K+ endpoints, 1M+ metrics/min
├─ Multi-region Kafka clusters
├─ Spark Streaming (instead of Flink)
├─ TimescaleDB Citus cluster (100+ nodes)
├─ Kubernetes auto-scaling: 50-200 pods
└─ CQRS pattern: separate read/write paths
```

### Performance Tuning

```
Kafka:
  - Increase num_partitions (aim for 10-100 per topic)
  - Increase compression (snappy or zstd)
  - Tune batch.size and linger.ms for throughput

Flink:
  - Increase parallelism (= num_partitions × 2-4)
  - Tune state backend (RocksDB for large state)
  - Adjust checkpoint frequency (balance latency vs overhead)

TimescaleDB:
  - Enable compression (saves 90%+ storage)
  - Tune chunk_time_interval (smaller = better compression, more CPU)
  - Optimize indexes (time + endpointID combinations)
  - Read replicas for dashboard queries

FastAPI:
  - Increase worker processes (cpu_count × 2-4)
  - Add Redis caching (hot queries: <50ms)
  - Implement query pagination
  - Use connection pooling (50-100 connections)
```

---

## Troubleshooting Quick Guide

### Issue: Alert Lag (Detection > 5 minutes)

```
Diagnose:
  1. Check Kafka consumer lag: kafka-consumer-groups
  2. Check Flink checkpoint status: Flink UI
  3. Check database write latency: Prometheus metrics

Solutions:
  - Increase Flink parallelism
  - Increase Kafka partitions
  - Optimize window computation
  - Check database stats (VACUUM, ANALYZE)
```

### Issue: High False Positive Rate (>10%)

```
Solutions:
  1. Increase anomaly threshold (0.70 → 0.75-0.80)
  2. Adjust ensemble weights (reduce sensitive models)
  3. Update baseline statistics (EWMA tuning)
  4. Add metric quality checks (skip bad data)
  5. Review model performance on recent data
```

### Issue: RCA Confidence Too Low (<80%)

```
Solutions:
  1. Ensure service dependency graph is complete
  2. Enable distributed tracing (OpenTelemetry)
  3. Verify baseline statistics are accurate
  4. Check for sufficient historical data (~30 days)
  5. Validate time synchronization across services
```

### Issue: Dashboard Slow (<500ms target)

```
Solutions:
  1. Add Redis caching for hot queries
  2. Implement query result pagination
  3. Create materialized views in TimescaleDB
  4. Add CDN for static assets
  5. Optimize React bundle (code splitting)
```

---

## Key Metrics to Monitor (Meta-Monitoring)

```
System Health:
  ✓ Alert detection latency (target: <1 min)
  ✓ Alert delivery success rate (target: >99.9%)
  ✓ Dashboard API response time (target: <500ms p95)
  ✓ Kafka consumer lag (target: <2 min)

Data Quality:
  ✓ Data loss rate (target: <0.001%)
  ✓ Metric completeness (target: >99%)
  ✓ Baseline freshness (updated daily)
  ✓ Distribution drift percentage

ML Model Quality:
  ✓ Anomaly detection precision (target: >95%)
  ✓ Anomaly detection recall (target: >80%)
  ✓ RCA accuracy vs ground truth (target: >90%)
  ✓ Model inference latency (target: <500ms)

Infrastructure:
  ✓ Kafka broker availability (target: >99.95%)
  ✓ Flink checkpoint health
  ✓ TimescaleDB replication lag
  ✓ Disk usage (alerts if >80%)
```

---

## Integration Checklist (Before Production)

```
☐ Prometheus exporters deployed to all services
☐ Distributed tracing (OpenTelemetry) enabled
☐ Kafka cluster tested for failover
☐ TimescaleDB backups automated
☐ Redis cluster HA configured
☐ Flink state backend persisted to distributed storage
☐ API TLS certificates configured
☐ Database authentication secure
☐ Alert channels (Slack, PagerDuty) connected
☐ User authentication (OIDC/SAML) integrated
☐ Audit logging enabled
☐ Rate limiting configured
☐ Monitoring dashboards created
☐ Runbooks written for on-call
☐ Load test completed (target throughput verified)
☐ Failover/disaster recovery tested
☐ Documentation updated
```

---

## Support Contacts

```
Architecture Questions:  See ARCHITECTURE.md
Implementation Details: See IMPLEMENTATION_STRATEGY.md
API Documentation:      See /docs endpoint
Deployment Guide:       See DEPLOYMENT.md
Troubleshooting:        See this document
```
