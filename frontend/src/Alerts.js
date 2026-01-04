import React, { useState, useEffect } from 'react';

function Alerts() {
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    fetchAlerts();
  }, []);

  const fetchAlerts = async () => {
    try {
      const response = await fetch('/alerts');
      const data = await response.json();
      setAlerts(data);
    } catch (error) {
      console.error('Failed to fetch alerts:', error);
    }
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

  return (
    <section>
      <h2>Alerts</h2>
      <table className="alerts-table">
        <thead>
          <tr>
            <th>Severity</th>
            <th>Endpoint</th>
            <th>Explanation</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {alerts.length === 0 ? (
            <tr>
              <td colSpan="4" style={{ textAlign: 'center', padding: '32px', color: '#6b7280' }}>
                No alerts found
              </td>
            </tr>
          ) : (
            alerts.map((alert, index) => (
              <tr key={index}>
                <td>
                  <span className={`severity-badge ${getSeverityClass(alert.severity)}`}>
                    {alert.severity || 'INFO'}
                  </span>
                </td>
                <td>{alert.endpoint || 'N/A'}</td>
                <td>{alert.explanation || 'No explanation available'}</td>
                <td>{formatTime(alert.timestamp_range?.end || alert.timestamp)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}

export default Alerts;