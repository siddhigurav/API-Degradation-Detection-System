import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import './CausalGraph.css';

const API_BASE = 'http://localhost:8000/api/v1';

export default function CausalGraph({ incidentId }) {
  const canvasRef = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadGraphData();
  }, [incidentId]);

  const loadGraphData = async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API_BASE}/rca/${incidentId}`);
      
      // Build graph from RCA data
      const graph = buildGraph(res.data);
      setData(graph);
      
      // Draw if canvas available
      if (canvasRef.current) {
        drawGraph(canvasRef.current, graph);
      }
    } catch (error) {
      console.error('Failed to load graph:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="causal-graph">
      <div className="graph-header">
        <h2>Causal Analysis Graph</h2>
        <p>Root causes → Contributing factors → Symptoms</p>
      </div>
      
      {loading ? (
        <div className="graph-loading">Loading causal graph...</div>
      ) : (
        <canvas 
          ref={canvasRef} 
          className="graph-canvas"
          width={800}
          height={600}
        />
      )}
      
      <div className="graph-legend">
        <div className="legend-item root-cause">
          <div className="legend-color"></div>
          <span>Root Cause</span>
        </div>
        <div className="legend-item contributing">
          <div className="legend-color"></div>
          <span>Contributing Factor</span>
        </div>
        <div className="legend-item symptom">
          <div className="legend-color"></div>
          <span>Symptom</span>
        </div>
      </div>
    </div>
  );
}

function buildGraph(rcaData) {
  const nodes = [];
  const edges = [];
  
  // Root causes
  rcaData.root_causes?.forEach((cause, idx) => {
    nodes.push({
      id: `root_${idx}`,
      label: cause.metric_name,
      type: 'root_cause',
      deviation: cause.deviation_percentage
    });
  });
  
  // Contributing factors
  rcaData.contributing_factors?.forEach((factor, idx) => {
    nodes.push({
      id: `contrib_${idx}`,
      label: factor.metric_name,
      type: 'contributing',
      deviation: factor.deviation_percentage
    });
    
    // Edge from root cause to contributing
    if (nodes.length > 1) {
      edges.push({
        from: nodes[0].id,
        to: `contrib_${idx}`
      });
    }
  });
  
  // Symptoms
  rcaData.symptoms?.forEach((symptom, idx) => {
    nodes.push({
      id: `symptom_${idx}`,
      label: symptom.metric_name,
      type: 'symptom',
      deviation: symptom.deviation_percentage
    });
    
    // Edge from contributing to symptom
    if (nodes.length > 1) {
      const lastContrib = nodes.filter(n => n.type === 'contributing').pop();
      if (lastContrib) {
        edges.push({
          from: lastContrib.id,
          to: `symptom_${idx}`
        });
      }
    }
  });
  
  return { nodes, edges };
}

function drawGraph(canvas, graph) {
  const ctx = canvas.getContext('2d');
  const width = canvas.width;
  const height = canvas.height;
  
  // Clear canvas
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, width, height);
  
  // Layout nodes in columns
  const columns = {
    root_cause: [],
    contributing: [],
    symptom: []
  };
  
  graph.nodes.forEach(node => {
    if (columns[node.type]) {
      columns[node.type].push(node);
    }
  });
  
  const positions = {};
  const columnWidth = width / 3;
  let colIdx = 0;
  
  for (const [type, nodes] of Object.entries(columns)) {
    const x = (colIdx + 0.5) * columnWidth;
    nodes.forEach((node, idx) => {
      const y = ((idx + 1) / (nodes.length + 1)) * height;
      positions[node.id] = { x, y };
    });
    colIdx++;
  }
  
  // Draw edges
  ctx.strokeStyle = '#ccc';
  ctx.lineWidth = 2;
  
  graph.edges.forEach(edge => {
    const from = positions[edge.from];
    const to = positions[edge.to];
    
    if (from && to) {
      ctx.beginPath();
      ctx.moveTo(from.x, from.y);
      // Bezier curve
      const cpX = (from.x + to.x) / 2;
      ctx.quadraticCurveTo(cpX, from.y, to.x, to.y);
      ctx.stroke();
      
      // Arrow
      const dx = to.x - from.x;
      const dy = to.y - from.y;
      const angle = Math.atan2(dy, dx);
      
      ctx.fillStyle = '#ccc';
      ctx.beginPath();
      ctx.moveTo(to.x, to.y);
      ctx.lineTo(to.x - 10 * Math.cos(angle - Math.PI / 6), to.y - 10 * Math.sin(angle - Math.PI / 6));
      ctx.lineTo(to.x - 10 * Math.cos(angle + Math.PI / 6), to.y - 10 * Math.sin(angle + Math.PI / 6));
      ctx.fill();
    }
  });
  
  // Draw nodes
  graph.nodes.forEach(node => {
    const pos = positions[node.id];
    if (!pos) return;
    
    const radius = 40;
    
    // Node color
    let fillColor;
    switch (node.type) {
      case 'root_cause':
        fillColor = '#dc3545';
        break;
      case 'contributing':
        fillColor = '#ffc107';
        break;
      case 'symptom':
        fillColor = '#17a2b8';
        break;
      default:
        fillColor = '#6c757d';
    }
    
    // Draw circle
    ctx.fillStyle = fillColor;
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
    ctx.fill();
    
    // Draw border
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 2;
    ctx.stroke();
    
    // Draw text
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 12px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    
    const lines = wrapText(node.label, 10);
    lines.forEach((line, idx) => {
      ctx.fillText(line, pos.x, pos.y - (lines.length - 1) * 6 + idx * 12);
    });
  });
}

function wrapText(text, maxChars) {
  const lines = [];
  let line = '';
  
  for (let char of text) {
    if ((line + char).length > maxChars) {
      lines.push(line);
      line = char;
    } else {
      line += char;
    }
  }
  
  if (line) lines.push(line);
  return lines;
}
