import React, { useState, useEffect } from 'react';

function Metrics() {
  const [metrics, setMetrics] = useState([]);

  useEffect(() => {
    fetchMetrics();
  }, []);

  const fetchMetrics = async () => {
    try {
      const response = await fetch('/metrics/checkout?window=15');
      const data = await response.json();
      setMetrics(data);
    } catch (error) {
      console.error('Failed to fetch metrics:', error);
      // Use mock data for development
      setMetrics([
        { window_end: new Date(Date.now() - 900000).toISOString(), p95_latency: 120, avg_latency: 80, error_rate: 0.02 },
        { window_end: new Date(Date.now() - 780000).toISOString(), p95_latency: 130, avg_latency: 85, error_rate: 0.02 },
        { window_end: new Date(Date.now() - 660000).toISOString(), p95_latency: 140, avg_latency: 90, error_rate: 0.03 },
        { window_end: new Date(Date.now() - 540000).toISOString(), p95_latency: 200, avg_latency: 150, error_rate: 0.05 },
        { window_end: new Date(Date.now() - 420000).toISOString(), p95_latency: 400, avg_latency: 300, error_rate: 0.08 },
        { window_end: new Date(Date.now() - 300000).toISOString(), p95_latency: 800, avg_latency: 600, error_rate: 0.12 },
        { window_end: new Date(Date.now() - 180000).toISOString(), p95_latency: 1000, avg_latency: 750, error_rate: 0.15 },
        { window_end: new Date(Date.now() - 60000).toISOString(), p95_latency: 1200, avg_latency: 800, error_rate: 0.18 }
      ]);
    }
  };

  // Simple line chart component
  const LineChart = ({ data, width = 800, height = 300 }) => {
    if (!data || data.length === 0) {
      return (
        <div style={{ width, height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280' }}>
          No data available
        </div>
      );
    }

    // Sort data by time
    const sortedData = [...data].sort((a, b) => new Date(a.window_end) - new Date(b.window_end));

    // Get p95 latency values
    const values = sortedData.map(d => d.p95_latency || 0);
    const maxValue = Math.max(...values);
    const minValue = Math.min(...values);

    // Chart dimensions
    const padding = 60;
    const chartWidth = width - padding * 2;
    const chartHeight = height - padding * 2;

    // Scale functions
    const xScale = (index) => (index / (sortedData.length - 1)) * chartWidth + padding;
    const yScale = (value) => chartHeight - ((value - minValue) / (maxValue - minValue)) * chartHeight + padding;

    // Generate path
    const pathData = sortedData.map((d, i) => {
      const x = xScale(i);
      const y = yScale(d.p95_latency || 0);
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    }).join(' ');

    // Format time labels
    const formatTime = (timestamp) => {
      try {
        const date = new Date(timestamp);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      } catch {
        return timestamp;
      }
    };

    return (
      <svg width={width} height={height} style={{ backgroundColor: '#ffffff' }}>
        {/* Grid lines */}
        <defs>
          <pattern id="grid" width="40" height="20" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 20" fill="none" stroke="#f3f4f6" strokeWidth="1"/>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />

        {/* Y-axis labels */}
        {[0, 0.25, 0.5, 0.75, 1].map(ratio => {
          const value = minValue + (maxValue - minValue) * ratio;
          const y = chartHeight - (ratio * chartHeight) + padding;
          return (
            <g key={ratio}>
              <text x={padding - 10} y={y + 4} textAnchor="end" fontSize="12" fill="#6b7280">
                {Math.round(value)}
              </text>
              <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="#e5e7eb" strokeWidth="1" />
            </g>
          );
        })}

        {/* X-axis labels */}
        {sortedData.map((d, i) => {
          if (i % Math.ceil(sortedData.length / 5) === 0) {
            const x = xScale(i);
            return (
              <text key={i} x={x} y={height - padding + 20} textAnchor="middle" fontSize="12" fill="#6b7280">
                {formatTime(d.window_end)}
              </text>
            );
          }
          return null;
        })}

        {/* Line */}
        <path
          d={pathData}
          fill="none"
          stroke="#2563eb"
          strokeWidth="2"
        />

        {/* Data points */}
        {sortedData.map((d, i) => (
          <circle
            key={i}
            cx={xScale(i)}
            cy={yScale(d.p95_latency || 0)}
            r="3"
            fill="#2563eb"
          />
        ))}
      </svg>
    );
  };

  return (
    <section className="metrics-section">
      <h2>Endpoint Metrics</h2>
      <div className="metrics-subtitle">p95 latency</div>
      <div className="chart-container">
        <LineChart data={metrics} />
      </div>
    </section>
  );
}

export default Metrics;