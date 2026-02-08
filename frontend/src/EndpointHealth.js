import React, { useState, useEffect } from 'react';
import { getAlerts } from './services/api';

function EndpointHealth() {
  const [endpoints, setEndpoints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const response = await getAlerts();
      const alerts = response.data.alerts || [];

      // Aggregate by endpoint
      const map = {};
      alerts.forEach(a => {
        const ep = a.endpoint || 'unknown';
        if (!map[ep]) map[ep] = { endpoint: ep, lastAlertTs: null, highestSeverity: 'INFO', count: 0 };
        map[ep].count = (map[ep].count || 0) + 1;
        // severity ranking
        const rank = (s) => {
          if (!s) return 0;
          const v = s.toString().toLowerCase();
          if (v.includes('crit') || v === 'high') return 3;
          if (v.includes('warn') || v === 'medium') return 2;
          return 1;
        };
        const currentRank = rank(map[ep].highestSeverity);
        const thisRank = rank(a.severity);
        if (thisRank > currentRank) map[ep].highestSeverity = a.severity || map[ep].highestSeverity;

        // last alert timestamp
        try {
          const ts = a.timestamp ? new Date(a.timestamp).getTime() : 0;
          if (!map[ep].lastAlertTs || ts > map[ep].lastAlertTs) map[ep].lastAlertTs = ts;
        } catch (e) {}
      });

      const list = Object.values(map).map(e => {
        // determine status
        const sev = (e.highestSeverity || '').toString().toLowerCase();
        const status = (sev.includes('crit') || sev === 'high' || sev === 'warn' || sev === 'medium') ? 'Degrading' : 'Healthy';
        // last alert human
        const last = e.lastAlertTs ? (() => {
          const mins = Math.round((Date.now() - e.lastAlertTs) / 60000);
          return mins <= 0 ? 'now' : `${mins} min ago`;
        })() : '—';

        return { endpoint: e.endpoint, status, lastAlert: last };
      });

      setEndpoints(list);
      setError(null);
    } catch (err) {
      console.error('Failed to load endpoints', err);
      setError('Failed to load endpoint health');
      setEndpoints([]);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <section>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h2>Endpoint Health</h2>
          <div style={{ color: '#6b7280', marginTop: '6px' }}>Overview of endpoint status</div>
        </div>
        <button onClick={fetchData} style={{ backgroundColor: '#2563eb', color: 'white', border: 'none', padding: '8px 16px', borderRadius: 6, cursor: 'pointer' }}>Refresh</button>
      </div>

      <table className="alerts-table">
        <thead>
          <tr>
            <th>Endpoint</th>
            <th>Status</th>
            <th>Last Alert</th>
          </tr>
        </thead>
        <tbody>
          {endpoints.length === 0 ? (
            <tr>
              <td colSpan="3" style={{ textAlign: 'center', padding: '32px', color: '#6b7280' }}>No endpoints or alerts available</td>
            </tr>
          ) : (
            endpoints.map((e, i) => (
              <tr key={e.endpoint + i}>
                <td style={{ fontWeight: 600 }}>{e.endpoint}</td>
                <td>{e.status}</td>
                <td>{e.lastAlert}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}

export default EndpointHealth;
