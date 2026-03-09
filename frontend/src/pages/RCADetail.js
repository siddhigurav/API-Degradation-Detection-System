import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './RCADetail.css';

const API_BASE = 'http://localhost:8000/api/v1';

export default function RCADetail({ incidentId }) {
  const [rca, setRca] = useState(null);
  const [similar, setSimilar] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadRCAData();
  }, [incidentId]);

  const loadRCAData = async () => {
    try {
      setLoading(true);
      
      const [rcaRes, similarRes] = await Promise.all([
        axios.get(`${API_BASE}/rca/${incidentId}`),
        axios.get(`${API_BASE}/rca/${incidentId}/similar`)
      ]);
      
      setRca(rcaRes.data);
      setSimilar(similarRes.data.similar_incidents || []);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load RCA data');
      console.error('Error loading RCA:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="rca-detail loading">Loading RCA analysis...</div>;
  }

  if (error) {
    return <div className="rca-detail error">Error: {error}</div>;
  }

  if (!rca) {
    return <div className="rca-detail error">RCA not found</div>;
  }

  return (
    <div className="rca-detail">
      <div className="rca-header">
        <h1>Root Cause Analysis</h1>
        <div className="incident-info">
          <span className="incident-id">Incident: {rca.incident_id}</span>
          <span className="timestamp">{new Date(rca.created_at).toLocaleString()}</span>
          <span className={`confidence confidence-${Math.round(rca.confidence * 100)}`}>
            Confidence: {(rca.confidence * 100).toFixed(1)}%
          </span>
        </div>
      </div>

      <div className="rca-content">
        {/* Anomaly Summary */}
        <section className="rca-section">
          <h2>Anomaly Summary</h2>
          <div className="summary-grid">
            <div className="summary-item">
              <label>Endpoint</label>
              <value>{rca.endpoint}</value>
            </div>
            <div className="summary-item">
              <label>Anomalous Metric</label>
              <value>{rca.anomalous_metric}</value>
            </div>
            <div className="summary-item">
              <label>Time to Mitigation</label>
              <value>{rca.ttd_seconds ? `${rca.ttd_seconds}s` : 'N/A'}</value>
            </div>
          </div>
        </section>

        {/* Root Causes */}
        <section className="rca-section">
          <h2>Root Causes</h2>
          <div className="findings-list">
            {rca.root_causes?.map((cause, idx) => (
              <div key={idx} className="finding finding-root-cause">
                <div className="finding-header">
                  <span className="badge root-cause">ROOT CAUSE</span>
                  <span className="metric-name">{cause.metric_name}</span>
                </div>
                <div className="finding-details">
                  <p><strong>Deviation:</strong> {cause.deviation_percentage?.toFixed(1)}%</p>
                  <p><strong>Evidence:</strong> {cause.evidence}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Contributing Factors */}
        {rca.contributing_factors?.length > 0 && (
          <section className="rca-section">
            <h2>Contributing Factors</h2>
            <div className="findings-list">
              {rca.contributing_factors.map((factor, idx) => (
                <div key={idx} className="finding finding-contributing">
                  <div className="finding-header">
                    <span className="badge contributing">CONTRIBUTING</span>
                    <span className="metric-name">{factor.metric_name}</span>
                  </div>
                  <div className="finding-details">
                    <p><strong>Impact:</strong> {factor.deviation_percentage?.toFixed(1)}%</p>
                    <p><strong>Evidence:</strong> {factor.evidence}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Symptoms */}
        {rca.symptoms?.length > 0 && (
          <section className="rca-section">
            <h2>Downstream Effects (Symptoms)</h2>
            <div className="findings-list">
              {rca.symptoms.map((symptom, idx) => (
                <div key={idx} className="finding finding-symptom">
                  <div className="finding-header">
                    <span className="badge symptom">SYMPTOM</span>
                    <span className="metric-name">{symptom.metric_name}</span>
                  </div>
                  <div className="finding-details">
                    <p><strong>Impact:</strong> {symptom.deviation_percentage?.toFixed(1)}%</p>
                    <p><strong>Evidence:</strong> {symptom.evidence}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Evidence */}
        <section className="rca-section">
          <h2>Analysis Evidence</h2>
          <div className="evidence-grid">
            {rca.evidence?.correlation_count !== undefined && (
              <div className="evidence-item">
                <label>Metric Correlations</label>
                <value>{rca.evidence.correlation_count}</value>
              </div>
            )}
            {rca.evidence?.causal_relationships !== undefined && (
              <div className="evidence-item">
                <label>Causal Relationships</label>
                <value>{rca.evidence.causal_relationships}</value>
              </div>
            )}
            {rca.evidence?.similar_incidents !== undefined && (
              <div className="evidence-item">
                <label>Similar Incidents</label>
                <value>{rca.evidence.similar_incidents}</value>
              </div>
            )}
            <div className="evidence-item">
              <label>Cascade Risk</label>
              <value>{rca.evidence?.cascade_risk ? '⚠️ High' : '✓ Low'}</value>
            </div>
          </div>
        </section>

        {/* Recommendations */}
        <section className="rca-section">
          <h2>Recommendations</h2>
          <div className="recommendations">
            <p>{rca.recommendations}</p>
          </div>
        </section>

        {/* Similar Incidents */}
        {similar.length > 0 && (
          <section className="rca-section">
            <h2>Similar Historical Incidents</h2>
            <div className="similar-incidents">
              {similar.map((incident, idx) => (
                <div key={idx} className="similar-incident">
                  <div className="incident-header">
                    <span className="similarity-score">
                      {(incident.similarity_score * 100).toFixed(0)}% Similar
                    </span>
                    <span className="incident-id">{incident.incident_id}</span>
                  </div>
                  <div className="incident-details">
                    <p><strong>Metric:</strong> {incident.anomalous_metric}</p>
                    <p><strong>TTM:</strong> {incident.time_to_mitigation_seconds}s</p>
                    <p><strong>Resolution:</strong> {incident.resolution_summary}</p>
                  </div>
                  <button className="btn-apply" onClick={() => applyResolution(incident.resolution_summary)}>
                    Apply Resolution
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function applyResolution(resolution) {
  alert(`Applying resolution:\n${resolution}`);
  // In production, would trigger remediation actions
}
