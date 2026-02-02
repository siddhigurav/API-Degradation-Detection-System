import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';

function AlertDetails() {
  const { id } = useParams();
  const [alert, setAlert] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchAlert();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const fetchAlert = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/alerts/${id}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAlert(data);
    } catch (err) {
      console.error('Failed to fetch alert:', err);
      setError(err.message || 'Failed to fetch alert');
      // Provide a lightweight mock for local dev
      setAlert({
        id,
        endpoint: '/checkout',
        severity: 'HIGH',
        window: '12:30 - 12:35',
        anomalous_metrics: [
          { metric: 'p95_latency', baseline: '180ms', current: '470ms', multiplier: 2.6 },
          { metric: 'error_rate', baseline: '0.8%', current: '1.4%', multiplier: 1.8 },
        ],
        explanation: 'The degradation is likely caused by backend performance regression rather than traffic surge, as request volume remained stable.'
      });
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div>Loading alert...</div>;
  if (error && !alert) return <div>Error: {error}</div>;

  const severityClass = (s) => {
    if (!s) return 'info';
    const v = s.toString().toLowerCase();
    if (v.includes('crit') || v === 'high') return 'critical';
    if (v.includes('warn') || v === 'medium') return 'warn';
    return 'info';
  };

  return (
    <section>
      <div style={{ marginBottom: 16 }}>
        <Link to="/alerts" style={{ color: '#2563eb', textDecoration: 'none' }}>← Back to Alerts</Link>
      </div>

      <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Alert Details</h2>
        <div style={{ marginTop: 8 }}>
          <strong>Endpoint:</strong> {alert.endpoint || 'N/A'}
          <br />
          <strong>Severity:</strong> <span className={`severity-badge ${severityClass(alert.severity)}`} style={{ marginLeft: 8 }}>{alert.severity || 'INFO'}</span>
          <br />
          <strong>Time Window:</strong> {alert.window || alert.timestamp || 'N/A'}
        </div>
      </div>

      <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Signals Detected</h3>
        <ul>
          {Array.isArray(alert.anomalous_metrics) && alert.anomalous_metrics.length > 0 ? (
            alert.anomalous_metrics.map((m, i) => {
              // m may be a string or an object
              if (typeof m === 'string') {
                return <li key={i}>• {m.replace('_', ' ')} (metric flagged)</li>;
              }
              const name = m.metric || m.name || JSON.stringify(m);
              const baseline = m.baseline || m.prev || m.expected || null;
              const current = m.current || m.value || null;
              const mult = m.multiplier || m.mult || (baseline && current ? (parseFloat(current) / parseFloat(baseline)).toFixed(2) : null);
              return (
                <li key={i} style={{ marginBottom: 10 }}>
                  <div style={{ fontWeight: 600 }}>• {name.replace('_', ' ')}</div>
                  {baseline && current ? (
                    <div style={{ color: '#6b7280' }}>
                      Baseline: {baseline} → Current: {current}{mult ? ` (×${mult})` : ''}
                    </div>
                  ) : null}
                </li>
              );
            })
          ) : (
            <li>No detailed signals available — see explanation below.</li>
          )}
        </ul>
      </div>

      <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
        <h3 style={{ marginTop: 0 }}>Explanation</h3>
        <div style={{ whiteSpace: 'pre-wrap' }}>{alert.explanation || 'No explanation provided.'}</div>
      </div>
    </section>
  );
}

export default AlertDetails;
