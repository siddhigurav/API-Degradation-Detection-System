-- PostgreSQL initialization script for alerts and incidents

CREATE EXTENSION IF NOT EXISTS uuid-ossp;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARN', 'CRITICAL')),
    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'acknowledged', 'resolved', 'closed')),
    title TEXT,
    signals JSONB NOT NULL DEFAULT '[]'::jsonb,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    explanation TEXT,
    insights JSONB DEFAULT '[]'::jsonb,
    recommendations JSONB DEFAULT '[]'::jsonb,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    resolution_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alerts_endpoint ON alerts(endpoint);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_alerts_status ON alerts(status);
CREATE INDEX idx_alerts_created ON alerts(created_at DESC);
CREATE INDEX idx_alerts_window ON alerts(window_start, window_end);

-- Incidents table
CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARN', 'CRITICAL')),
    title TEXT NOT NULL,
    description TEXT,
    root_cause TEXT,
    root_cause_confidence FLOAT CHECK (root_cause_confidence >= 0 AND root_cause_confidence <= 1),
    affected_services JSONB DEFAULT '[]'::jsonb,  -- array of service names
    affected_components JSONB DEFAULT '[]'::jsonb,
    timeline JSONB DEFAULT '[]'::jsonb,  -- array of events
    remediation_actions JSONB DEFAULT '[]'::jsonb,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration_seconds INTEGER,
    user_impact_count INTEGER,
    estimated_revenue_impact NUMERIC(12, 2),
    status TEXT DEFAULT 'ongoing' CHECK (status IN ('ongoing', 'resolved', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_incidents_endpoint ON incidents(endpoint);
CREATE INDEX idx_incidents_severity ON incidents(severity);
CREATE INDEX idx_incidents_status ON incidents(status);
CREATE INDEX idx_incidents_created ON incidents(created_at DESC);
CREATE INDEX idx_incidents_time_range ON incidents(start_time, end_time);

-- Root cause analyses
CREATE TABLE IF NOT EXISTS root_cause_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
    alert_ids UUID[] DEFAULT '{}',
    root_cause TEXT NOT NULL,
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence JSONB DEFAULT '[]'::jsonb,  -- array of evidence strings
    affected_components JSONB DEFAULT '[]'::jsonb,
    supporting_metrics JSONB DEFAULT '[]'::jsonb,
    metric_correlations JSONB DEFAULT '{}',  -- correlation matrix
    temporal_analysis JSONB DEFAULT '{}',  -- which metrics changed first
    remediation_suggestions JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rca_incident ON root_cause_analyses(incident_id);
CREATE INDEX idx_rca_created ON root_cause_analyses(created_at DESC);

-- Alert history (audit trail)
CREATE TABLE IF NOT EXISTS alert_history (
    id SERIAL PRIMARY KEY,
    alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    action TEXT NOT NULL,  -- created, acknowledged, resolved, commented
    actor TEXT,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alert_history_alert ON alert_history(alert_id);
CREATE INDEX idx_alert_history_created ON alert_history(created_at DESC);

-- Alert deduplication tracking
CREATE TABLE IF NOT EXISTS alert_dedup_cache (
    id SERIAL PRIMARY KEY,
    endpoint TEXT NOT NULL,
    severity TEXT NOT NULL,
    hash TEXT NOT NULL,  -- hash of alert content
    last_alert_time TIMESTAMPTZ NOT NULL,
    UNIQUE(endpoint, severity, hash)
);

CREATE INDEX idx_alert_dedup_cache_endpoint ON alert_dedup_cache(endpoint);

-- Alert cooldown tracking
CREATE TABLE IF NOT EXISTS alert_cooldown (
    id SERIAL PRIMARY KEY,
    endpoint TEXT NOT NULL,
    severity TEXT NOT NULL,
    cooldown_until TIMESTAMPTZ NOT NULL,
    UNIQUE(endpoint, severity)
);

-- Model predictions for evaluation
CREATE TABLE IF NOT EXISTS model_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint TEXT NOT NULL,
    metric_window JSONB NOT NULL,
    predicted_anomaly BOOLEAN,
    anomaly_probability FLOAT CHECK (anomaly_probability >= 0 AND anomaly_probability <= 1),
    predicted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actual_label BOOLEAN,
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX idx_model_predictions_endpoint ON model_predictions(endpoint);
CREATE INDEX idx_model_predictions_predicted_at ON model_predictions(predicted_at DESC);

-- Baseline statistics
CREATE TABLE IF NOT EXISTS baseline_statistics (
    id SERIAL PRIMARY KEY,
    endpoint TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    window_minutes INTEGER,  -- 1, 5, 15, 60
    baseline_mean FLOAT,
    baseline_stddev FLOAT,
    baseline_ewma FLOAT,
    baseline_ewma_stddev FLOAT,
    p50 FLOAT,
    p95 FLOAT,
    p99 FLOAT,
    min_observed FLOAT,
    max_observed FLOAT,
    sample_count INTEGER,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(endpoint, metric_name, window_minutes)
);

CREATE INDEX idx_baseline_endpoint ON baseline_statistics(endpoint);
CREATE INDEX idx_baseline_updated ON baseline_statistics(last_updated DESC);

-- System configuration
CREATE TABLE IF NOT EXISTS system_config (
    id SERIAL PRIMARY KEY,
    config_key TEXT UNIQUE NOT NULL,
    config_value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Insert default configurations
INSERT INTO system_config (config_key, config_value, description) VALUES
    ('anomaly_detection_threshold', '0.5', 'Anomaly confidence threshold'),
    ('alert_dedup_window_seconds', '600', 'Alert deduplication window'),
    ('alert_cooldown_info_seconds', '3600', 'Cooldown for INFO alerts'),
    ('alert_cooldown_warn_seconds', '1800', 'Cooldown for WARN alerts'),
    ('alert_cooldown_critical_seconds', '300', 'Cooldown for CRITICAL alerts'),
    ('min_consecutive_anomalies', '3', 'Min consecutive anomalies to alert'),
    ('rca_confidence_threshold', '0.5', 'Min confidence for RCA suggestions'),
    ('metrics_retention_days', '365', 'Metrics data retention in days'),
    ('model_retraining_interval_days', '7', 'Model retraining interval'),
    ('max_metric_cardinality', '100000', 'Max unique metric combinations')
ON CONFLICT (config_key) DO NOTHING;

-- Tenants table (for multi-tenancy support)
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    api_key TEXT UNIQUE NOT NULL,
    webhook_url TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tenants_api_key ON tenants(api_key);

-- Service registry (for distributed system health)
CREATE TABLE IF NOT EXISTS service_registry (
    id SERIAL PRIMARY KEY,
    service_name TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    status TEXT DEFAULT 'up' CHECK (status IN ('up', 'down', 'degraded')),
    health_check_url TEXT,
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,
    UNIQUE(service_name, instance_id)
);

CREATE INDEX idx_service_registry_name ON service_registry(service_name);
CREATE INDEX idx_service_registry_heartbeat ON service_registry(last_heartbeat DESC);

-- Create trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_alerts_updated_at BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_incidents_updated_at BEFORE UPDATE ON incidents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT USAGE ON SCHEMA public TO monitoring;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO monitoring;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO monitoring;

SELECT 'PostgreSQL schema initialized successfully!' as status;
