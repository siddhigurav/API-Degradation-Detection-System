# API Degradation Detection System - Architecture Diagram

## High-Level System Architecture

```mermaid
graph TB
    subgraph "API Services Layer"
        S1["Service A"]
        S2["Service B"]
        S3["Service C"]
        S4["Service D"]
    end

    subgraph "Metrics Collection"
        P1["Prometheus Exporter"]
        OT1["OpenTelemetry Collector"]
        CE["Custom Exporters"]
    end

    subgraph "Streaming Layer"
        K["Kafka Cluster"]
        K1["raw-metrics"]
        K2["processed-metrics"]
        K3["anomalies"]
        K4["incidents"]
    end

    subgraph "Stream Processing"
        FPS["Feature Processing Service<br/>Flink/Spark"]
        FPS1["Windowing Engine"]
        FPS2["Baseline Calculator"]
        FPS3["Drift Detector"]
    end

    subgraph "AI/ML Engines"
        AD["Anomaly Detection Engine"]
        LSTM["LSTM Autoencoder"]
        IF["Isolation Forest"]
        STAT["Statistical Methods"]
        PROPHET["Prophet TS"]
    end

    subgraph "Root Cause Analysis"
        RCA["RCA Engine"]
        CAUSAL["Causal Analysis"]
        TRACE["Trace Correlation"]
        DEP["Dependency Analysis"]
    end

    subgraph "Alert & Incident Management"
        AM["Alert Manager"]
        DED["Deduplication Engine"]
        ROUTE["Alert Router"]
        NOTIF["Notification Service"]
    end

    subgraph "Storage Layer"
        TSDB["TimescaleDB<br/>Metrics & Events"]
        PG["PostgreSQL<br/>Metadata & Config"]
        REDIS["Redis<br/>Cache & Pub/Sub"]
    end

    subgraph "Dashboard & API"
        API["FastAPI Query Server"]
        DASH["React Dashboard"]
        CONFIG["Configuration UI"]
    end

    subgraph "Notifications"
        SLACK["Slack"]
        PD["PagerDuty"]
        EMAIL["Email"]
    end

    %% Connections
    S1 --> P1
    S2 --> P1
    S3 --> OT1
    S4 --> OT1
    S1 --> CE
    
    P1 --> K1
    OT1 --> K1
    CE --> K1
    
    K1 --> FPS
    FPS --> FPS1
    FPS --> FPS2
    FPS --> FPS3
    FPS --> K2
    
    K2 --> AD
    AD --> LSTM
    AD --> IF
    AD --> STAT
    AD --> PROPHET
    AD --> K3
    
    K3 --> RCA
    RCA --> CAUSAL
    RCA --> TRACE
    RCA --> DEP
    RCA --> K4
    
    K4 --> AM
    AM --> DED
    AM --> ROUTE
    AM --> NOTIF
    
    FPS --> TSDB
    AD --> TSDB
    RCA --> TSDB
    AM --> TSDB
    
    TSDB --> API
    PG --> API
    REDIS --> API
    
    API --> DASH
    API --> CONFIG
    REDIS --> DASH
    
    NOTIF --> SLACK
    NOTIF --> PD
    NOTIF --> EMAIL
    
    DASH -.WebSocket.-> REDIS
```

## Component Interaction Diagram

```mermaid
graph LR
    subgraph "Real-Time Processing Pipeline"
        RAW["Raw Metrics<br/>Kafka"]
        FP["Feature Processing"]
        PROC["Processed Metrics<br/>Kafka"]
        AD["Anomaly Detection"]
        ANOM["Anomalies<br/>Kafka"]
    end

    subgraph "RCA & Alerting"
        RCA["Root Cause Analysis"]
        AMW["Alert Manager"]
        INC["Incidents<br/>Kafka"]
    end

    subgraph "Persistence"
        CACHE["Redis Cache"]
        DB["TimescaleDB"]
    end

    subgraph "Presentation"
        API["Query API"]
        DASH["Dashboard"]
    end

    RAW -->|throughput: 100K-1M/sec| FP
    FP -->|latency: 1-5 min| PROC
    PROC -->|throughput: 50K-500K/sec| AD
    AD -->|latency: 100-500ms| ANOM
    ANOM -->|latency: 500ms-5sec| RCA
    RCA -->|confidence scores| AMW
    AMW -->|incident created| INC
    
    ANOM -->|write| DB
    PROC -->|write| DB
    INC -->|write| DB
    
    AD -->|update state| CACHE
    ANOM -->|publish| CACHE
    
    DB -->|query| API
    CACHE -->|query| API
    API -->|REST/WebSocket| DASH
```

## Data Model Architecture

```mermaid
graph TD
    subgraph "Kafka Topics"
        T1["raw-metrics<br/>endpoint, timestamp, latency, error_rate, volume"]
        T2["processed-metrics<br/>endpoint, window, agg_latency, agg_errors, features"]
        T3["anomalies<br/>endpoint, metric, anomaly_score, severity, timestamp"]
        T4["incidents<br/>incident_id, affected_endpoints, root_causes, status"]
    end

    subgraph "TimescaleDB Hypertables"
        HT1["metrics (timeseries)<br/>time, endpoint, metric_name, value"]
        HT2["anomalies (events)<br/>time, endpoint, anomaly_type, score, confidence"]
        HT3["incidents (events)<br/>time, incident_id, root_causes, status"]
        HT4["alerts (events)<br/>time, alert_id, severity, channel, delivered"]
    end

    subgraph "PostgreSQL Tables"
        PT1["service_dependencies<br/>source_id, target_id, latency_impact, confidence"]
        PT2["users<br/>user_id, username, role, email"]
        PT3["alert_rules<br/>rule_id, endpoint, metric, threshold, actions"]
        PT4["baselines<br/>endpoint, metric, baseline_mean, stddev, updated_at"]
    end

    subgraph "Redis Keys"
        RK1["alerts:{incident_id} → set"]
        RK2["metrics:current:{endpoint} → hash (realtime)"]
        RK3["user:session:{session_id} → auth data"]
        RK4["anomaly:queue → list (pending RCA)"]
    end

    T1 --> HT1
    T2 --> HT2
    T3 --> HT3
    T4 --> HT4
    
    HT1 -.-> PT4
    HT2 -.-> PT3
    HT4 -.-> PT3
    
    T3 --> RK1
    HT1 --> RK2
```

## Service Communication Matrix

```mermaid
graph TB
    subgraph "Synchronous APIs"
        A1["Dashboard ← QueryAPI<br/>GET /alerts, /incidents, /metrics"]
        A2["QueryAPI → TimescaleDB<br/>SQL queries for timeseries"]
        A3["QueryAPI → PostgreSQL<br/>Config & metadata"]
        A4["Dashboard → ConfigAPI<br/>PUT alert rules, service deps"]
    end

    subgraph "Asynchronous Messaging"
        B1["Feature Processing ← KafkaConsumer<br/>raw-metrics topic"]
        B2["Feature Processing → KafkaProducer<br/>processed-metrics topic"]
        B3["Anomaly Engine ← KafkaConsumer<br/>processed-metrics topic"]
        B4["Anomaly Engine → KafkaProducer<br/>anomalies topic"]
        B5["RCA Engine ← KafkaConsumer<br/>anomalies topic"]
        B6["RCA Engine → KafkaProducer<br/>incidents topic"]
    end

    subgraph "Real-Time Updates"
        C1["Alert Manager ← KafkaConsumer<br/>incidents topic"]
        C2["Alert Manager → Redis.PUBLISH<br/>incident:new channel"]
        C3["Dashboard ← WebSocket<br/>Subscribe to incident:new"]
    end

    subgraph "Batch Jobs"
        D1["Model Retraining<br/>Daily: query historical data"]
        D2["RCA Cache Warmup<br/>Hourly: precompute common scenarios"]
        D3["Data Archival<br/>Weekly: compress old data"]
    end
```

## Deployment Architecture (Kubernetes)

```mermaid
graph TB
    subgraph "Production K8s Cluster"
        subgraph "kafka-ns"
            K["Kafka StatefulSet<br/>3 replicas"]
            KZ["ZooKeeper<br/>3 replicas"]
        end

        subgraph "processing-ns"
            JM["Flink JobManager"]
            TM1["Flink TaskManager 1"]
            TM2["Flink TaskManager 2"]
            TM3["Flink TaskManager 3"]
        end

        subgraph "api-ns"
            API1["FastAPI Pod 1"]
            API2["FastAPI Pod 2"]
            API3["FastAPI Pod 3"]
            LB["LoadBalancer Service"]
        end

        subgraph "ml-ns"
            AD["Anomaly Detection<br/>CronJob (every 1min)"]
            RCA["RCA Service<br/>Deployment"]
        end

        subgraph "storage-ns"
            TSDB["TimescaleDB<br/>StatefulSet"]
            PG["PostgreSQL<br/>Primary + Replica"]
            REDIS["Redis Cluster<br/>6 nodes"]
        end

        subgraph "frontend-ns"
            NX["Nginx Ingress"]
            DASH["React SPA<br/>Multiple replicas"]
        end
    end

    subgraph "External Services"
        SLACK["Slack API"]
        PD["PagerDuty API"]
        SMTP["SMTP Server"]
    end

    K --> TSDB
    KZ --> K
    JM --> TM1
    JM --> TM2
    JM --> TM3
    TM1 --> K
    API1 --> TSDB
    API1 --> REDIS
    API2 --> TSDB
    API2 --> REDIS
    API3 --> TSDB
    API3 --> REDIS
    LB --> API1
    LB --> API2
    LB --> API3
    AD --> K
    RCA --> K
    NX --> DASH
    LB --> SLACK
    LB --> PD
    LB --> SMTP
```

## ML Pipeline Architecture

```mermaid
graph TD
    subgraph "Training Pipeline"
        H["Historical Data<br/>90 days"]
        F["Feature Engineering<br/>Create LSTM features"]
        S["Train/Test Split"]
        T1["LSTM Autoencoder<br/>Training"]
        T2["Isolation Forest<br/>Training"]
        T3["Prophet<br/>Fitting"]
        V["Model Validation"]
        MR["Model Registry"]
    end

    subgraph "Inference Pipeline"
        IN["Incoming Metrics<br/>Real-time stream"]
        FE["Feature Engineering"]
        INF1["LSTM Inference<br/>Reconstruction error"]
        INF2["IF Inference<br/>Anomaly score"]
        INF3["Prophet Forecast<br/>Expected bounds"]
        STAT["Z-Score<br/>Baseline comparison"]
        VOTE["Ensemble Voting<br/>Aggregate scores"]
        OUT["Anomaly Output<br/>score + confidence"]
    end

    subgraph "Model Monitoring"
        DRIFT["Drift Detection<br/>KL divergence"]
        PERF["Performance Tracking<br/>precision, recall"]
        RETRAIN["Trigger Retraining<br/>if drift detected"]
    end

    H --> F
    F --> S
    S --> T1
    S --> T2
    S --> T3
    T1 --> V
    T2 --> V
    T3 --> V
    V --> MR

    IN --> FE
    FE --> INF1
    FE --> INF2
    FE --> INF3
    FE --> STAT
    INF1 --> VOTE
    INF2 --> VOTE
    INF3 --> VOTE
    STAT --> VOTE
    VOTE --> OUT
    
    OUT --> DRIFT
    DRIFT --> PERF
    PERF --> RETRAIN
    RETRAIN -.-> H
```

## Alert Deduplication & Correlation

```mermaid
graph LR
    subgraph "Raw Alerts"
        A1["Alert: db-service latency spike"]
        A2["Alert: payment-service error rate spike"]
        A3["Alert: api-gateway timeout"]
    end

    subgraph "Deduplication <br/>10-min window"
        D["Check: same endpoint<br/>+ same metric + same hour?"]
    end

    subgraph "Correlation <br/>Service dependency graph"
        C["Check: affected services<br/>share common upstream?"]
    end

    subgraph "Incident Grouping"
        G1["Incident-123<br/>Database degradation<br/>(3 correlated alerts)"]
        G2["Incident-124<br/>Payment processor<br/>timeout (1 alert)"]
    end

    A1 --> D
    A2 --> D
    A3 --> D
    D --> C
    C --> G1
    C --> G2
```

## RCA Process Flow

```mermaid
graph TD
    A["Anomaly Detected<br/>endpoint: payment-service<br/>metric: latency_p99"]
    B["Fetch Dependency Graph"]
    C["Get Distributed Traces<br/>for affected requests"]
    D{"Multi-Method RCA"}
    E1["Method 1: Causal Inference<br/>DoWhy"]
    E2["Method 2: Time-Series Correlation"]
    E3["Method 3: Trace Analysis"]
    F["Aggregate Results<br/>Weighted scoring"]
    G["Rank Root Causes<br/>by confidence"]
    H["Generate Recommendations<br/>Remediation steps"]
    I["Publish RCA Results<br/>to incidents topic"]

    A --> B
    B --> C
    C --> D
    D --> E1
    D --> E2
    D --> E3
    E1 --> F
    E2 --> F
    E3 --> F
    F --> G
    G --> H
    H --> I
```

These diagrams visualize:
1. **Overall system architecture** with all major components
2. **Component interactions** and data flow timing
3. **Data model** in Kafka topics and databases
4. **Service communication patterns** (sync/async/realtime)
5. **Kubernetes deployment structure**
6. **ML training and inference pipelines**
7. **Alert deduplication and correlation logic**
8. **RCA analysis process**
