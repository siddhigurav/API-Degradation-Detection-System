-- TimescaleDB schema initialization for metrics storage

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS json_utils;

-- Main metrics table (hypertable)
CREATE TABLE IF NOT EXISTS metrics (
    time TIMESTAMPTZ NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT DEFAULT 'GET',
    status_code INTEGER,
    metric_name TEXT NOT NULL,
    metric_type TEXT,  -- gauge, counter, histogram, summary
    value FLOAT8 NOT NULL,
    min_value FLOAT8,
    max_value FLOAT8,
    count INTEGER,
    percentile_50 FLOAT8,
    percentile_95 FLOAT8,
    percentile_99 FLOAT8,
    labels JSONB DEFAULT '{}'::jsonb,
    PRIMARY KEY (time, endpoint, metric_name)
);

-- Convert to hypertable (1 day chunks)
SELECT create_hypertable('metrics', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_metrics_endpoint_time 
    ON metrics (endpoint, time DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_metric_name_time 
    ON metrics (metric_name, time DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_labels 
    ON metrics USING gin (labels);

-- Enable compression for old data (>30 days)
ALTER TABLE metrics SET (
    timescaledb.compress = true,
    timescaledb.compress_segmentby = 'endpoint,metric_name',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('metrics', INTERVAL '30 days', if_not_exists => TRUE);

-- Baselines table - stores statistical baselines for each metric per endpoint
CREATE TABLE IF NOT EXISTS metric_baselines (
    id SERIAL PRIMARY KEY,
    endpoint TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_type TEXT,
    baseline_mean FLOAT8,
    baseline_stddev FLOAT8,
    baseline_ewma FLOAT8,
    baseline_ewma_stddev FLOAT8,
    percentile_50 FLOAT8,
    percentile_95 FLOAT8,
    percentile_99 FLOAT8,
    sample_count INTEGER,
    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(endpoint, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_baselines_endpoint 
    ON metric_baselines (endpoint);
CREATE INDEX IF NOT EXISTS idx_baselines_updated 
    ON metric_baselines (last_updated DESC);

-- Anomalies table
CREATE TABLE IF NOT EXISTS anomalies (
    id SERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    endpoint TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value FLOAT8 NOT NULL,
    baseline_mean FLOAT8,
    baseline_stddev FLOAT8,
    z_score FLOAT8,
    deviation_ratio FLOAT8,
    severity TEXT,  -- LOW, MEDIUM, HIGH
    confidence FLOAT8,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_anomalies_time 
    ON anomalies (time DESC);
CREATE INDEX IF NOT EXISTS idx_anomalies_endpoint_time 
    ON anomalies (endpoint, time DESC);

-- Alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    alert_id UUID UNIQUE,
    endpoint TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT DEFAULT 'open',  -- open, acknowledged, resolved
    signals JSONB,  -- array of anomalies
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ,
    explanation TEXT,
    insights JSONB,  -- array of strings
    recommendations JSONB,  -- array of strings
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alerts_endpoint_time 
    ON alerts (endpoint, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_status 
    ON alerts (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_severity 
    ON alerts (severity, created_at DESC);

-- Incidents table
CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,
    incident_id UUID UNIQUE,
    endpoint TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT,
    description TEXT,
    root_cause TEXT,
    root_cause_confidence FLOAT8,
    affected_components JSONB,  -- array of components
    timeline JSONB,  -- array of events
    remediation_actions JSONB,  -- array of actions taken
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    duration_seconds INTEGER,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_incidents_endpoint_time 
    ON incidents (endpoint, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_status 
    ON incidents (severity, created_at DESC);

-- Root cause analysis results
CREATE TABLE IF NOT EXISTS root_cause_analyses (
    id SERIAL PRIMARY KEY,
    rca_id UUID UNIQUE,
    alert_id INTEGER REFERENCES alerts(id),
    root_cause TEXT NOT NULL,
    confidence FLOAT8,
    evidence JSONB,  -- array of evidence strings
    affected_components JSONB,  -- array of component info
    correlations JSONB,  -- correlation data
    remediation_suggestions JSONB,  -- array of suggestions
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rca_alert 
    ON root_cause_analyses (alert_id);
CREATE INDEX IF NOT EXISTS idx_rca_created 
    ON root_cause_analyses (created_at DESC);

-- Model performance tracking
CREATE TABLE IF NOT EXISTS model_evaluations (
    id SERIAL PRIMARY KEY,
    evaluation_date DATE NOT NULL UNIQUE,
    precision FLOAT8,
    recall FLOAT8,
    f1_score FLOAT8,
    false_positive_rate FLOAT8,
    false_negative_rate FLOAT8,
    roc_auc FLOAT8,
    avg_precision FLOAT8,
    true_positives INTEGER,
    false_positives INTEGER,
    true_negatives INTEGER,
    false_negatives INTEGER,
    detection_latency_mean FLOAT8,  -- seconds
    detection_latency_p95 FLOAT8,
    detection_latency_p99 FLOAT8,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Feature store (pre-computed features for ML)
CREATE TABLE IF NOT EXISTS features (
    time TIMESTAMPTZ NOT NULL,
    endpoint TEXT NOT NULL,
    feature_vector FLOAT8[] NOT NULL,  -- array of floats
    feature_names TEXT[] NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (time, endpoint)
);

SELECT create_hypertable('features', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');

CREATE INDEX IF NOT EXISTS idx_features_endpoint_time 
    ON features (endpoint, time DESC);

-- System health metrics
CREATE TABLE IF NOT EXISTS system_health (
    id SERIAL PRIMARY KEY,
    service_name TEXT NOT NULL,
    health_status TEXT,  -- healthy, degraded, unhealthy
    error_count INTEGER,
    error_message TEXT,
    metrics JSONB,
    checked_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_system_health_service 
    ON system_health (service_name, checked_at DESC);

-- Audit log
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    user_id TEXT,
    changes JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_created 
    ON audit_log (created_at DESC);

-- Continuous aggregate for 1-minute aggregation
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_1m AS
SELECT 
    time_bucket('1 minute', time) as bucket,
    endpoint,
    metric_name,
    AVG(value) as avg_value,
    MIN(value) as min_value,
    MAX(value) as max_value,
    STDDEV(value) as stddev_value,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value) as p50_value,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value) as p95_value,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY value) as p99_value,
    COUNT(*) as count
FROM metrics
GROUP BY bucket, endpoint, metric_name;

-- Continuously aggregated view for 5-minute aggregation
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_5m AS
SELECT 
    time_bucket('5 minutes', time) as bucket,
    endpoint,
    metric_name,
    AVG(value) as avg_value,
    MIN(value) as min_value,
    MAX(value) as max_value,
    STDDEV(value) as stddev_value,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value) as p50_value,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value) as p95_value,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY value) as p99_value,
    COUNT(*) as count
FROM metrics
WHERE time > now() - INTERVAL '7 days'
GROUP BY bucket, endpoint, metric_name;

-- Grant permissions
GRANT USAGE ON SCHEMA public TO monitoring;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO monitoring;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO monitoring;

-- Print success message
SELECT 'TimescaleDB schema initialized successfully!' as status;
