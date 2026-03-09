import React, { useState, useEffect, useRef } from 'react';
import './AdvancedDashboard.css';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, HeatMapChart, BarChart, Bar } from 'recharts';

/**
 * Service Dependency Graph Component
 * Visualizes service relationships and health status
 */
const ServiceDependencyGraph = ({ data }) => {
  const canvasRef = useRef(null);
  const [selectedService, setSelectedService] = useState(null);

  useEffect(() => {
    if (!canvasRef.current || !data) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    
    // Set canvas size
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;

    // Clear canvas
    ctx.fillStyle = '#f8f9fa';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw nodes (services)
    const nodeRadius = 30;
    const padding = 60;
    const services = data.services || [];
    
    // Position services in circle
    const angle = (2 * Math.PI) / services.length;
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = Math.min(canvas.width, canvas.height) / 2 - padding;

    const nodePositions = {};

    // Draw edges first (so they appear behind nodes)
    ctx.strokeStyle = '#ccc';
    ctx.lineWidth = 2;

    data.dependencies?.forEach(dep => {
      const start = nodePositions[dep.from];
      const end = nodePositions[dep.to];
      
      if (start && end) {
        ctx.beginPath();
        ctx.moveTo(start.x, start.y);
        ctx.lineTo(end.x, end.y);
        ctx.stroke();

        // Draw arrow
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const headlen = 15;
        const angle = Math.atan2(dy, dx);

        ctx.fillStyle = '#666';
        ctx.beginPath();
        ctx.moveTo(end.x, end.y);
        ctx.lineTo(end.x - headlen * Math.cos(angle - Math.PI / 6), end.y - headlen * Math.sin(angle - Math.PI / 6));
        ctx.lineTo(end.x - headlen * Math.cos(angle + Math.PI / 6), end.y - headlen * Math.sin(angle + Math.PI / 6));
        ctx.closePath();
        ctx.fill();
      }
    });

    // Draw nodes
    services.forEach((service, i) => {
      const x = centerX + radius * Math.cos(angle * i - Math.PI / 2);
      const y = centerY + radius * Math.sin(angle * i - Math.PI / 2);
      
      nodePositions[service.name] = { x, y };

      // Determine node color based on health
      const healthColor = 
        service.health === 'healthy' ? '#28a745' :
        service.health === 'degraded' ? '#ffc107' :
        '#dc3545';

      // Draw circle
      ctx.fillStyle = healthColor;
      ctx.beginPath();
      ctx.arc(x, y, nodeRadius, 0, 2 * Math.PI);
      ctx.fill();

      // Draw border
      ctx.strokeStyle = selectedService === service.name ? '#000' : '#fff';
      ctx.lineWidth = selectedService === service.name ? 3 : 2;
      ctx.stroke();

      // Draw text
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 12px Arial';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(service.name, x, y - 8);
      ctx.font = '10px Arial';
      ctx.fillText(`(${service.status})`, x, y + 8);
    });

    // Add click handling for service selection
    canvas.addEventListener('click', (e) => {
      const rect = canvas.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;

      Object.entries(nodePositions).forEach(([service, pos]) => {
        const dist = Math.sqrt((clickX - pos.x) ** 2 + (clickY - pos.y) ** 2);
        if (dist <= nodeRadius) {
          setSelectedService(service === selectedService ? null : service);
        }
      });
    });

  }, [data, selectedService]);

  return (
    <div className="service-dependency">
      <h3>Service Dependency Graph</h3>
      <canvas ref={canvasRef} className="dependency-canvas" />
      {selectedService && (
        <div className="service-details">
          <strong>{selectedService}</strong>
          <p>Dependencies: 3</p>
          <p>Dependents: 2</p>
          <p>Health: Healthy</p>
        </div>
      )}
    </div>
  );
};

/**
 * Health Heatmap Component
 * Shows service health over time
 */
const HealthHeatmap = ({ data }) => {
  const heatmapData = data?.heatmap || [];

  return (
    <div className="health-heatmap">
      <h3>Service Health Timeline (24h)</h3>
      <div className="heatmap-grid">
        {heatmapData.map((service, idx) => (
          <div key={idx} className="heatmap-row">
            <div className="service-name">{service.name}</div>
            <div className="heatmap-cells">
              {service.timeline?.map((health, timeIdx) => {
                const color =
                  health === 'healthy' ? '#28a745' :
                  health === 'degraded' ? '#ffc107' :
                  health === 'unhealthy' ? '#dc3545' :
                  '#e9ecef';
                
                return (
                  <div
                    key={timeIdx}
                    className="heatmap-cell"
                    style={{ backgroundColor: color }}
                    title={`${service.name} at ${timeIdx}:00 - ${health}`}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="heatmap-legend">
        <span style={{ color: '#28a745' }}>✓ Healthy</span>
        <span style={{ color: '#ffc107' }}>⚠ Degraded</span>
        <span style={{ color: '#dc3545' }}>✗ Unhealthy</span>
      </div>
    </div>
  );
};

/**
 * Trend Analysis Component
 * Shows metric trends with forecasting
 */
const TrendAnalysis = ({ data }) => {
  const [selectedMetric, setSelectedMetric] = useState(0);

  const metrics = data?.trends || [];
  const selectedTrend = metrics[selectedMetric];

  return (
    <div className="trend-analysis">
      <h3>Metric Trends & Forecast</h3>
      
      <div className="metric-selector">
        {metrics.map((metric, idx) => (
          <button
            key={idx}
            className={`metric-btn ${idx === selectedMetric ? 'active' : ''}`}
            onClick={() => setSelectedMetric(idx)}
          >
            {metric.name}
          </button>
        ))}
      </div>

      {selectedTrend && (
        <>
          <div className="trend-stats">
            <div className="stat">
              <span>Current:</span>
              <strong>{selectedTrend.current?.value?.toFixed(2)}</strong>
            </div>
            <div className="stat">
              <span>7d Avg:</span>
              <strong>{selectedTrend.avg_7d?.toFixed(2)}</strong>
            </div>
            <div className="stat">
              <span>Trend:</span>
              <strong className={selectedTrend.trend === 'up' ? 'text-danger' : 'text-success'}>
                {selectedTrend.trend === 'up' ? '📈' : '📉'} {selectedTrend.change_percent?.toFixed(2)}%
              </strong>
            </div>
            <div className="stat">
              <span>Forecast (24h):</span>
              <strong>{selectedTrend.forecast_24h?.toFixed(2)}</strong>
            </div>
          </div>

          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={selectedTrend.data || []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" angle={-45} textAnchor="end" height={80} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="actual"
                stroke="#0066cc"
                name="Actual"
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="forecast"
                stroke="#ff9800"
                name="Forecast"
                strokeDasharray="5 5"
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="upper_bound"
                stroke="#ccc"
                name="Upper Bound"
                isAnimationActive={false}
                strokeOpacity={0.3}
              />
              <Line
                type="monotone"
                dataKey="lower_bound"
                stroke="#ccc"
                name="Lower Bound"
                isAnimationActive={false}
                strokeOpacity={0.3}
              />
            </LineChart>
          </ResponsiveContainer>

          {selectedTrend.anomalies?.length > 0 && (
            <div className="anomalies">
              <h4>Recent Anomalies</h4>
              <ul>
                {selectedTrend.anomalies.map((anom, idx) => (
                  <li key={idx}>
                    <strong>{anom.timestamp}</strong>: {anom.description}
                    <span className={`severity-${anom.severity}`}>{anom.severity}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
};

/**
 * Advanced Dashboard
 * Combines all advanced visualizations
 */
const AdvancedDashboard = () => {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('24h');

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        
        // Fetch dashboard data
        const response = await fetch(`/api/v1/advanced-dashboard?time_range=${timeRange}`);
        const data = await response.json();
        
        setDashboardData(data);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
        setDashboardData(null);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [timeRange]);

  if (loading) {
    return <div className="advanced-dashboard">Loading...</div>;
  }

  return (
    <div className="advanced-dashboard">
      <div className="dashboard-header">
        <h1>Advanced Analytics Dashboard</h1>
        <div className="time-selector">
          {['1h', '6h', '24h', '7d', '30d'].map(range => (
            <button
              key={range}
              className={`time-btn ${timeRange === range ? 'active' : ''}`}
              onClick={() => setTimeRange(range)}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="grid-item full-width">
          <ServiceDependencyGraph data={dashboardData?.dependencies} />
        </div>

        <div className="grid-item full-width">
          <HealthHeatmap data={dashboardData?.health} />
        </div>

        <div className="grid-item full-width">
          <TrendAnalysis data={dashboardData?.trends} />
        </div>
      </div>
    </div>
  );
};

export default AdvancedDashboard;
