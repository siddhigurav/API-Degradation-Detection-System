import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [expandedAlert, setExpandedAlert] = useState(null);

  useEffect(() => {
    fetchAlerts();
  }, []);

  const fetchAlerts = async () => {
    try {
      const response = await fetch('/alerts');
      const data = await response.json();
      setAlerts(data.alerts || []);
    } catch (error) {
      console.error('Failed to fetch alerts:', error);
      // Use mock data for development
      setAlerts([
        {
          id: 'mock-1',
          endpoint: '/checkout',
          severity: 'CRITICAL',
          explanation: '🚨 CRITICAL ALERT: /checkout endpoint showing degradation over the last 5m.\n\n📈 WHAT CHANGED:\n• Average latency increased from 120ms to 800ms (+567%)\n• P95 latency increased from 180ms to 1200ms (+567%)\n• Error rate increased from 2% to 15% (+650%)\n\n📊 WHAT STAYED STABLE:\n• Request volume remained consistent\n\n💡 RECOMMENDATIONS:\n• Check database connection performance\n• Review recent code deployments\n• Monitor server CPU/memory usage',
          timestamp: new Date().toISOString(),
          metrics_involved: ['avg_latency', 'p95_latency', 'error_rate']
        },
        {
          id: 'mock-2',
          endpoint: '/api/users',
          severity: 'WARNING',
          explanation: '⚠️ WARNING: /api/users endpoint showing moderate degradation.\n\n📈 WHAT CHANGED:\n• Average latency increased from 80ms to 200ms (+150%)\n\n📊 WHAT STAYED STABLE:\n• Error rates remained low\n• Request volume consistent\n\n💡 RECOMMENDATIONS:\n• Monitor for further degradation\n• Check for increased database load',
          timestamp: new Date(Date.now() - 300000).toISOString(),
          metrics_involved: ['avg_latency']
        }
      ]);
    }
  };

  const toggleExpanded = (alertId) => {
    setExpandedAlert(expandedAlert === alertId ? null : alertId);
  };

  const truncateExplanation = (text, maxLength = 100) => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  const getSeverityClass = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'critical':
        return 'critical';
      case 'warn':
      case 'warning':
        return 'warn';
      case 'info':
        return 'info';
      default:
        return 'info';
    }
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return 'N/A';
    try {
      const date = new Date(timestamp);
      return date.toLocaleString();
    } catch {
      return timestamp;
    }
  };

  const computeSignals = (alert) => {
    if (!alert) return 0;
    if (alert.anomaly_count != null) return alert.anomaly_count;
    if (Array.isArray(alert.metrics_involved)) return alert.metrics_involved.length;
    if (Array.isArray(alert.anomalous_metrics)) return alert.anomalous_metrics.length;
    return 1;
  };

  const sinceMinutes = (timestamp) => {
    if (!timestamp) return 'N/A';
    try {
      const diffMs = Date.now() - new Date(timestamp).getTime();
      const mins = Math.max(0, Math.round(diffMs / 60000));
      return `${mins} min`;
    } catch {
      return 'N/A';
    }
  };

  return (
    <section>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2>Active Alerts</h2>
          <div style={{ color: '#6b7280', marginTop: '6px' }}>Default landing page</div>
        </div>
        <button 
          onClick={fetchAlerts}
          style={{
            backgroundColor: '#2563eb',
            color: 'white',
            border: 'none',
            padding: '8px 16px',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '14px'
          }}
        >
          Refresh
        </button>
      </div>

      <table className="alerts-table">
        <thead>
          <tr>
            <th>Endpoint</th>
            <th>Severity</th>
            <th>Signals</th>
            <th>Since</th>
          </tr>
        </thead>
        <tbody>
          {alerts.length === 0 ? (
            <tr>
              <td colSpan="4" style={{ textAlign: 'center', padding: '32px', color: '#6b7280' }}>
                No active alerts
              </td>
            </tr>
          ) : (
            alerts.map((alert, index) => (
              <tr key={alert.id || index}>
                <td style={{ fontWeight: 600 }}>{alert.endpoint || 'N/A'}</td>
                <td>
                  <span className={`severity-badge ${getSeverityClass(alert.severity)}`}>
                    {alert.severity || 'INFO'}
                  </span>
                </td>
                <td>{computeSignals(alert)}</td>
                <td>{sinceMinutes(alert.timestamp)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}

export default Alerts;