import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './Dashboard.css';

const API_BASE = 'http://localhost:8000/api/v1';

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [activeIncidents, setActiveIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedHours, setSelectedHours] = useState(24);

  useEffect(() => {
    loadDashboardData();
    
    // Refresh every 30 seconds
    const interval = setInterval(loadDashboardData, 30000);
    return () => clearInterval(interval);
  }, [selectedHours]);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      
      const [summaryRes, timelineRes, incidentsRes] = await Promise.all([
        axios.get(`${API_BASE}/dashboard/summary?hours=${selectedHours}`),
        axios.get(`${API_BASE}/dashboard/timeline?hours=${selectedHours}&granularity=1hour`),
        axios.get(`${API_BASE}/incidents/active?limit=50`)
      ]);
      
      setSummary(summaryRes.data);
      setTimeline(timelineRes.data.data || []);
      setActiveIncidents(incidentsRes.data.incidents || []);
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="dashboard loading">Loading...</div>;
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>API Degradation Detection System</h1>
        <div className="controls">
          <select 
            value={selectedHours} 
            onChange={(e) => setSelectedHours(Number(e.target.value))}
          >
            <option value={1}>Last hour</option>
            <option value={6}>Last 6 hours</option>
            <option value={24}>Last 24 hours</option>
            <option value={168}>Last 7 days</option>
          </select>
          <button onClick={loadDashboardData}>Refresh</button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards">
        <div className="card">
          <h3>Total Alerts</h3>
          <div className="value">
            {(summary?.alerts_by_severity?.CRITICAL || 0) + 
             (summary?.alerts_by_severity?.WARNING || 0) +
             (summary?.alerts_by_severity?.INFO || 0)}
          </div>
          <div className="breakdown">
            <span className="critical">Critical: {summary?.alerts_by_severity?.CRITICAL || 0}</span>
            <span className="warning">Warning: {summary?.alerts_by_severity?.WARNING || 0}</span>
          </div>
        </div>

        <div className="card">
          <h3>RCA Analyses</h3>
          <div className="value">{summary?.rca_statistics?.total_rcas || 0}</div>
          <div className="breakdown">
            Avg Confidence: {summary?.rca_statistics?.avg_confidence?.toFixed(2) || 'N/A'}
          </div>
        </div>

        <div className="card">
          <h3>Avg Time to Mitigation</h3>
          <div className="value">{Math.round(summary?.rca_statistics?.avg_ttd || 0)}s</div>
          <div className="breakdown">
            Min: {summary?.rca_statistics?.min_ttd}s | 
            Max: {summary?.rca_statistics?.max_ttd}s
          </div>
        </div>

        <div className="card">
          <h3>System Health</h3>
          <div className="value health-good">●</div>
          <div className="breakdown">All systems operational</div>
        </div>
      </div>

      {/* Charts */}
      <div className="charts-section">
        <div className="chart-container">
          <h2>Incidents Timeline</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={timeline}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time_bucket" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="alert_count" stroke="#8884d8" name="Total Alerts" />
              <Line type="monotone" dataKey="critical_count" stroke="#ff0000" name="Critical" />
              <Line type="monotone" dataKey="warning_count" stroke="#ffa500" name="Warning" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-container">
          <h2>Top Affected Endpoints</h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={summary?.top_affected_endpoints || []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="endpoint" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="incident_count" fill="#8884d8" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Active Incidents Table */}
      <div className="incidents-section">
        <h2>Active Incidents ({activeIncidents.length})</h2>
        <div className="incidents-table">
          <table>
            <thead>
              <tr>
                <th>Incident ID</th>
                <th>Endpoint</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {activeIncidents.map((incident) => (
                <tr key={incident.incident_id} className={`severity-${incident.severity?.toLowerCase()}`}>
                  <td>{incident.incident_id}</td>
                  <td>{incident.endpoint}</td>
                  <td><span className={`badge severity-${incident.severity?.toLowerCase()}`}>{incident.severity}</span></td>
                  <td>{incident.acknowledged ? 'Acknowledged' : 'New'}</td>
                  <td>{new Date(incident.created_at).toLocaleString()}</td>
                  <td>
                    <button className="btn-small" onClick={() => handleViewRCA(incident.incident_id)}>View RCA</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function handleViewRCA(incidentId) {
  window.location.href = `/rca/${incidentId}`;
}
