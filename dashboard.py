"""
Minimal Dashboard for API Degradation Detection System

A Flask-based web dashboard showing:
- Endpoint health scores
- Drift timelines
- Alert history

Run with: python dashboard.py
"""

import os
import sys
import io
import base64
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template_string, request
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Updated imports for better IDE resolution (explicit path)
from src.storage.metrics_store import get_metrics_store
from src.storage.alert_store import get_alert_store
from src.storage.baseline_store import get_baseline_store
from config import STORAGE_BACKEND

app = Flask(__name__)

# Initialize storage
metrics_store = get_metrics_store(STORAGE_BACKEND)
alert_store = get_alert_store(STORAGE_BACKEND)
baseline_store = get_baseline_store(STORAGE_BACKEND)

def get_endpoint_health_scores():
    """Calculate health scores for all endpoints based on recent metrics and alerts."""
    # Get all recent metrics (last 24 hours)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=24)

    all_metrics = metrics_store.get_metrics(
        start_time=start_time,
        end_time=end_time
    )

    if all_metrics.empty:
        return {}

    # Get recent alerts
    recent_alerts = alert_store.get_recent_alerts(hours=24)

    # Calculate health scores per endpoint
    health_scores = {}

    for endpoint in all_metrics['endpoint'].unique():
        endpoint_data = all_metrics[all_metrics['endpoint'] == endpoint]

        # Get latest metrics
        latest_metrics = endpoint_data.sort_values('window_end').groupby('window_minutes').last().reset_index()

        # Calculate health score (0-100, higher is better)
        score = 100

        # Check latency (lower is better)
        if 'avg_latency' in latest_metrics.columns:
            avg_latency = latest_metrics['avg_latency'].mean()
            if avg_latency > 500:  # ms
                score -= 30
            elif avg_latency > 200:
                score -= 15

        # Check error rate (lower is better)
        if 'error_rate' in latest_metrics.columns:
            avg_error = latest_metrics['error_rate'].mean()
            if avg_error > 0.05:  # 5%
                score -= 40
            elif avg_error > 0.01:  # 1%
                score -= 20

        # Check for recent alerts (reduce score)
        endpoint_alerts = [a for a in recent_alerts if a.get('endpoint') == endpoint]
        if endpoint_alerts:
            # Reduce score based on severity and recency
            for alert in endpoint_alerts:
                severity = alert.get('severity', 'LOW')
                if severity == 'CRITICAL':
                    score -= 25
                elif severity == 'HIGH':
                    score -= 15
                elif severity == 'MEDIUM':
                    score -= 10

        health_scores[endpoint] = max(0, min(100, score))

    return health_scores

def get_drift_timelines(endpoint=None, hours=24):
    """Get drift timeline data for visualization."""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    # Get metrics data
    df = metrics_store.get_metrics(
        endpoint=endpoint,
        start_time=start_time,
        end_time=end_time
    )

    if df.empty:
        return pd.DataFrame()

    # Sort by time
    df = df.sort_values('window_end')

    return df

def get_recent_alerts(hours=24):
    """Get recent alerts for display."""
    all_alerts = alert_store.get_all_alerts(limit=100)

    # Filter by time
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    recent_alerts = []
    for alert in all_alerts:
        created_at_str = alert.get('created_at')
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                if created_at >= cutoff_time:
                    recent_alerts.append(alert)
            except:
                # If can't parse timestamp, include it
                recent_alerts.append(alert)

    return recent_alerts

def create_drift_plot(endpoint=None, hours=24):
    """Create matplotlib plot for drift timelines."""
    drift_data = get_drift_timelines(endpoint=endpoint, hours=hours)

    if drift_data.empty:
        # Create empty plot
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, 'No data available', ha='center', va='center', transform=ax.transAxes)
        ax.set_title('Drift Timeline - No Data')
    else:
        fig, ax1 = plt.subplots(figsize=(10, 6))

        # Plot latency on primary y-axis
        if 'avg_latency' in drift_data.columns:
            latency_data = drift_data.groupby('window_end')['avg_latency'].mean()
            ax1.plot(latency_data.index, latency_data.values, 'b-', label='Avg Latency (ms)', linewidth=2)

        ax1.set_xlabel('Time')
        ax1.set_ylabel('Latency (ms)', color='b')
        ax1.tick_params(axis='y', labelcolor='b')

        # Plot error rate on secondary y-axis
        if 'error_rate' in drift_data.columns:
            ax2 = ax1.twinx()
            error_data = drift_data.groupby('window_end')['error_rate'].mean() * 100  # Convert to percentage
            ax2.plot(error_data.index, error_data.values, 'r--', label='Error Rate (%)', linewidth=2)
            ax2.set_ylabel('Error Rate (%)', color='r')
            ax2.tick_params(axis='y', labelcolor='r')

        # Format x-axis
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

        title = f'Drift Timeline - {endpoint if endpoint else "All Endpoints"}'
        ax1.set_title(title)

        # Add legend
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels() if 'error_rate' in drift_data.columns else ([], [])
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

    plt.tight_layout()

    # Convert plot to base64 string
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close(fig)

    return image_base64

def get_severity_color(severity):
    """Get color for severity level."""
    colors = {
        'CRITICAL': '#dc3545',  # red
        'HIGH': '#fd7e14',     # orange
        'MEDIUM': '#ffc107',   # yellow
        'LOW': '#007bff',      # blue
        'INFO': '#6c757d'      # gray
    }
    return colors.get(severity, '#6c757d')

def get_health_color(score):
    """Get color for health score."""
    if score >= 80:
        return '#28a745'  # green
    elif score >= 60:
        return '#ffc107'  # yellow
    else:
        return '#dc3545'  # red

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚨 API Degradation Monitor</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f8f9fa;
            color: #333;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            color: #2c3e50;
            margin-bottom: 10px;
        }
        .header p {
            color: #7f8c8d;
            font-size: 1.1em;
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .card h3 {
            margin-top: 0;
            color: #2c3e50;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 10px;
        }
        .health-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #ecf0f1;
        }
        .health-score {
            font-weight: bold;
            font-size: 1.2em;
        }
        .alert-item {
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid;
        }
        .alert-title {
            font-weight: bold;
            margin-bottom: 5px;
        }
        .alert-time {
            color: #7f8c8d;
            font-size: 0.9em;
        }
        .alert-details {
            margin-top: 10px;
            font-size: 0.9em;
        }
        .metrics-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        .metrics-table th, .metrics-table td {
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid #ecf0f1;
        }
        .metrics-table th {
            background-color: #f8f9fa;
            font-weight: bold;
        }
        .plot-container {
            text-align: center;
            margin: 20px 0;
        }
        .plot-container img {
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .controls {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .controls form {
            display: flex;
            gap: 15px;
            align-items: center;
        }
        .controls select, .controls input {
            padding: 8px 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .controls button {
            background: #007bff;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
        }
        .controls button:hover {
            background: #0056b3;
        }
        .no-data {
            text-align: center;
            color: #7f8c8d;
            font-style: italic;
            padding: 40px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚨 API Degradation Monitor</h1>
            <p>Real-time monitoring of API performance and degradation patterns</p>
        </div>

        <div class="controls">
            <form method="GET">
                <label for="endpoint">Endpoint:</label>
                <select name="endpoint" id="endpoint">
                    <option value="">All Endpoints</option>
                    {% for ep in endpoints %}
                    <option value="{{ ep }}" {% if ep == selected_endpoint %}selected{% endif %}>{{ ep }}</option>
                    {% endfor %}
                </select>

                <label for="hours">Time Range:</label>
                <select name="hours" id="hours">
                    <option value="1" {% if time_range == 1 %}selected{% endif %}>1 hour</option>
                    <option value="6" {% if time_range == 6 %}selected{% endif %}>6 hours</option>
                    <option value="24" {% if time_range == 24 %}selected{% endif %}>24 hours</option>
                    <option value="72" {% if time_range == 72 %}selected{% endif %}>72 hours</option>
                </select>

                <button type="submit">Update</button>
            </form>
        </div>

        <div class="grid">
            <!-- Health Scores -->
            <div class="card">
                <h3>🏥 Endpoint Health Scores</h3>
                {% if health_scores %}
                {% for endpoint, score in health_scores.items() %}
                <div class="health-item">
                    <span>{{ endpoint }}</span>
                    <span class="health-score" style="color: {{ get_health_color(score) }};">
                        {{ score }}/100
                    </span>
                </div>
                {% endfor %}
                {% else %}
                <div class="no-data">No health data available</div>
                {% endif %}
            </div>

            <!-- Drift Timelines -->
            <div class="card">
                <h3>📈 Drift Timelines</h3>
                <div class="plot-container">
                    <img src="data:image/png;base64,{{ plot_image }}" alt="Drift Timeline">
                </div>
            </div>

            <!-- Alert History -->
            <div class="card">
                <h3>⚠️ Recent Alerts</h3>
                {% if recent_alerts %}
                {% for alert in recent_alerts[:8] %}
                <div class="alert-item" style="border-left-color: {{ get_severity_color(alert['severity']) }};">
                    <div class="alert-title">
                        {{ alert['severity'] }} - {{ alert['endpoint'] }}
                    </div>
                    <div class="alert-time">{{ alert['created_at'] }}</div>
                    <div class="alert-details">
                        {{ alert['explanation'] }}
                    </div>
                </div>
                {% endfor %}
                {% else %}
                <div class="no-data">No recent alerts</div>
                {% endif %}
            </div>
        </div>

        <!-- Detailed Metrics -->
        <div class="card">
            <h3>📊 Detailed Metrics</h3>
            {% if not detailed_data.empty %}
            <table class="metrics-table">
                <thead>
                    <tr>
                        <th>Endpoint</th>
                        <th>Time</th>
                        <th>Avg Latency</th>
                        <th>P95 Latency</th>
                        <th>Error Rate</th>
                        <th>Request Volume</th>
                    </tr>
                </thead>
                <tbody>
                    {% for _, row in detailed_data.tail(20).iterrows() %}
                    <tr>
                        <td>{{ row['endpoint'] }}</td>
                        <td>{{ row['window_end'].strftime('%Y-%m-%d %H:%M') if not pd.isna(row['window_end']) else '-' }}</td>
                        <td>{{ "%.1f"|format(row['avg_latency']) if not pd.isna(row['avg_latency']) else '-' }}</td>
                        <td>{{ "%.1f"|format(row['p95_latency']) if not pd.isna(row['p95_latency']) else '-' }}</td>
                        <td>{{ "%.3f"|format(row['error_rate']) if not pd.isna(row['error_rate']) else '-' }}</td>
                        <td>{{ row['request_volume'] if not pd.isna(row['request_volume']) else '-' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="no-data">No detailed metrics available</div>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    # Get query parameters
    selected_endpoint = request.args.get('endpoint', '')
    time_range = int(request.args.get('hours', 24))

    # Get data
    health_scores = get_endpoint_health_scores()
    endpoints = list(health_scores.keys())

    plot_image = create_drift_plot(
        endpoint=selected_endpoint if selected_endpoint else None,
        hours=time_range
    )

    recent_alerts = get_recent_alerts(hours=time_range)

    detailed_data = get_drift_timelines(
        endpoint=selected_endpoint if selected_endpoint else None,
        hours=time_range
    )

    # Render template
    return render_template_string(
        HTML_TEMPLATE,
        health_scores=health_scores,
        endpoints=endpoints,
        selected_endpoint=selected_endpoint,
        time_range=time_range,
        plot_image=plot_image,
        recent_alerts=recent_alerts,
        detailed_data=detailed_data,
        get_severity_color=get_severity_color,
        get_health_color=get_health_color,
        pd=pd
    )

if __name__ == '__main__':
    print("🚀 Starting API Degradation Monitor Dashboard...")
    print("📊 Open http://localhost:5000 in your browser")
    print("🔧 Initializing storage backends...")
    try:
        # Test storage connections
        print(f"📊 Metrics store: {type(metrics_store).__name__}")
        print(f"🚨 Alert store: {type(alert_store).__name__}")
        print(f"📈 Baseline store: {type(baseline_store).__name__}")
        print("✅ Storage backends initialized")
    except Exception as e:
        print(f"❌ Storage initialization error: {e}")
        sys.exit(1)
    
    app.run(debug=True, host='0.0.0.0', port=5000)