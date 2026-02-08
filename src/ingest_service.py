from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
import os
import json
from datetime import datetime
import asyncio

from aggregator import RollingMetricsAggregator
from storage.metrics_store import InMemoryMetricsStorage
from detector import update_baselines

app = FastAPI(title="EWS API Service")

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'data'))
RAW_LOGS = os.path.join(DATA_DIR, 'raw_logs.jsonl')
AGG_LOGS = os.path.join(DATA_DIR, 'aggregates.jsonl')
ALERTS_FILE = os.path.join(DATA_DIR, 'alerts.jsonl')

os.makedirs(DATA_DIR, exist_ok=True)

# Global aggregator instance
aggregator = RollingMetricsAggregator()

# Global metrics storage
metrics_store = InMemoryMetricsStorage()

# Load existing logs into aggregator at startup
def load_existing_logs():
    if os.path.exists(RAW_LOGS):
        with open(RAW_LOGS, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    log = json.loads(line)
                    aggregator.add_log(log)
                except Exception:
                    continue

load_existing_logs()

# Background task to store metrics periodically
async def store_metrics_periodically():
    while True:
        try:
            metrics = aggregator.get_metrics()
            # Flatten to list of dicts
            flattened = []
            now = datetime.utcnow()
            for endpoint, windows in metrics.items():
                for window_name, mets in windows.items():
                    window_min = int(window_name.split('_')[1][:-1])
                    rec = {
                        'endpoint': endpoint,
                        'window_minutes': window_min,
                        'timestamp': now,
                        'avg_latency': mets['avg_latency'],
                        'p50_latency': mets['p50_latency'],
                        'p95_latency': mets['p95_latency'],
                        'p99_latency': mets['p99_latency'],
                        'error_rate': mets['error_rate'],
                        'request_volume': mets['request_volume'],
                    }
                    flattened.append(rec)
            
            if flattened:
                metrics_store.store_metrics(flattened)
                
                # Update baselines with new metrics
                # Convert flattened metrics to the format expected by update_baselines
                current_metrics_for_baselines = {}
                for rec in flattened:
                    endpoint = rec['endpoint']
                    window_minutes = rec['window_minutes']
                    # Use a synthetic window_start key
                    window_key = f"window_{window_minutes}m"
                    
                    if endpoint not in current_metrics_for_baselines:
                        current_metrics_for_baselines[endpoint] = {}
                    
                    current_metrics_for_baselines[endpoint][window_key] = {
                        'avg_latency': rec['avg_latency'],
                        'p95_latency': rec['p95_latency'],
                        'error_rate': rec['error_rate']
                    }
                
                update_baselines(current_metrics_for_baselines)
                
        except Exception as e:
            print(f"Error storing metrics: {e}")
        
        await asyncio.sleep(60)  # Store every minute

# Start background task
asyncio.create_task(store_metrics_periodically())

class LogEntry(BaseModel):
    timestamp: Optional[str] = Field(None, description="ISO8601 timestamp. If omitted server time will be used.")
    endpoint: str
    status_code: int
    latency_ms: float
    response_size: int
    error_message: Optional[str] = None

def read_jsonl(file_path):
    if not os.path.exists(file_path):
        return []
    records = []
    with open(file_path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    return records

@app.get('/alerts', response_model=List[dict])
async def get_alerts(severity: Optional[str] = Query(None, description="Filter by severity: INFO, WARN, CRITICAL")):
    alerts = read_jsonl(ALERTS_FILE)
    if severity:
        alerts = [a for a in alerts if a.get('severity') == severity]
    
    # Add metrics_involved field to each alert
    for alert in alerts:
        if 'anomalies' in alert:
            alert['metrics_involved'] = [a.get('metric') for a in alert['anomalies']]
        else:
            alert['metrics_involved'] = []
    
    return alerts

@app.get('/alerts/{alert_id}', response_model=dict)
async def get_alert(alert_id: int):
    alerts = read_jsonl(ALERTS_FILE)
    if alert_id < 0 or alert_id >= len(alerts):
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert = alerts[alert_id].copy()
    
    # Add metrics_involved field
    if 'anomalies' in alert:
        alert['metrics_involved'] = [a.get('metric') for a in alert['anomalies']]
    else:
        alert['metrics_involved'] = []
    
    # Add alert_id to the response
    alert['alert_id'] = alert_id
    
    return alert

@app.get('/metrics')
async def get_all_metrics():
    metrics = aggregator.get_metrics()
    # Flatten to list of dicts like compute_aggregates
    result = []
    for endpoint, windows in metrics.items():
        for window_name, mets in windows.items():
            window_min = int(window_name.split('_')[1][:-1])  # e.g. window_1m -> 1
            rec = {
                'endpoint': endpoint,
                'window': f'{window_min}m',
                'avg_latency': mets['avg_latency'],
                'p95_latency': mets['p95_latency'],
                'error_rate': mets['error_rate'],
                'request_volume': mets['request_volume'],
                'timestamp': datetime.utcnow().isoformat().replace('+00:00', 'Z')
            }
            result.append(rec)
    return result

@app.post('/ingest')
async def ingest(log: LogEntry):
    record = log.dict()
    if not record.get('timestamp'):
        record['timestamp'] = datetime.utcnow().isoformat() + 'Z'
    try:
        with open(RAW_LOGS, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(record) + '\n')
        # Add to aggregator
        aggregator.add_log(record)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to write log: {e}")
    return {"status": "ok"}

@app.get('/health')
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
