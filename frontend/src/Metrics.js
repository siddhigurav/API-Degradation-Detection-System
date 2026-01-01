import React, { useState, useEffect } from 'react';

function Metrics() {
  const [endpoint, setEndpoint] = useState('/checkout');
  const [window, setWindow] = useState(15);
  const [metrics, setMetrics] = useState([]);

  useEffect(() => {
    if (endpoint) fetchMetrics();
  }, [endpoint, window]);

  const fetchMetrics = async () => {
    const url = `/metrics/${endpoint.replace('/', '')}?window=${window}`;
    const response = await fetch(url);
    const data = await response.json();
    setMetrics(data);
  };

  const isAnomalous = (metric, value) => {
    // Simple heuristic: highlight if value exceeds thresholds
    const thresholds = {
      avg_latency: 200,
      p95_latency: 500,
      error_rate: 0.05,
      response_size_variance: 1000
    };
    return value > thresholds[metric];
  };

  return (
    <div>
      <h2>Endpoint Metrics</h2>
      <input
        type="text"
        value={endpoint}
        onChange={(e) => setEndpoint(e.target.value)}
        placeholder="Enter endpoint, e.g., /checkout"
      />
      <select value={window} onChange={(e) => setWindow(Number(e.target.value))}>
        <option value={1}>1m</option>
        <option value={5}>5m</option>
        <option value={15}>15m</option>
      </select>
      <table>
        <thead>
          <tr>
            <th>Window End</th>
            <th>Avg Latency</th>
            <th>P95 Latency</th>
            <th>Error Rate</th>
            <th>Request Volume</th>
            <th>Response Size Variance</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m, index) => (
            <tr key={index}>
              <td>{m.window_end}</td>
              <td className={isAnomalous('avg_latency', m.avg_latency) ? 'anomalous' : ''}>{m.avg_latency?.toFixed(2)}</td>
              <td className={isAnomalous('p95_latency', m.p95_latency) ? 'anomalous' : ''}>{m.p95_latency?.toFixed(2)}</td>
              <td className={isAnomalous('error_rate', m.error_rate) ? 'anomalous' : ''}>{m.error_rate?.toFixed(3)}</td>
              <td>{m.request_volume}</td>
              <td className={isAnomalous('response_size_variance', m.response_size_variance) ? 'anomalous' : ''}>{m.response_size_variance?.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default Metrics;