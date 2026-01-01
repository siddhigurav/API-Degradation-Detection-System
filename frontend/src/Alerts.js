import React, { useState, useEffect } from 'react';

function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [severity, setSeverity] = useState('');

  useEffect(() => {
    fetchAlerts();
  }, [severity]);

  const fetchAlerts = async () => {
    const url = severity ? `/alerts?severity=${severity}` : '/alerts';
    const response = await fetch(url);
    const data = await response.json();
    setAlerts(data);
  };

  return (
    <div>
      <h2>Alerts</h2>
      <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
        <option value="">All</option>
        <option value="INFO">INFO</option>
        <option value="WARN">WARN</option>
        <option value="CRITICAL">CRITICAL</option>
      </select>
      <table>
        <thead>
          <tr>
            <th>Endpoint</th>
            <th>Severity</th>
            <th>Explanation</th>
            <th>Time Range</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert, index) => (
            <tr key={index}>
              <td>{alert.endpoint}</td>
              <td className={`severity-${alert.severity}`}>{alert.severity}</td>
              <td>{alert.explanation}</td>
              <td>{alert.timestamp_range?.end} ({alert.timestamp_range?.minutes}m)</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default Alerts;