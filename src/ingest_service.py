from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
import os
import json
from datetime import datetime

app = FastAPI(title="EWS API Service")

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'data'))
RAW_LOGS = os.path.join(DATA_DIR, 'raw_logs.jsonl')
AGG_LOGS = os.path.join(DATA_DIR, 'aggregates.jsonl')
ALERTS_FILE = os.path.join(DATA_DIR, 'alerts.jsonl')

os.makedirs(DATA_DIR, exist_ok=True)

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
    return alerts

@app.get('/metrics/{endpoint}', response_model=List[dict])
async def get_metrics(endpoint: str, window: Optional[int] = Query(None, description="Filter by window minutes: 1, 5, 15")):
    aggregates = read_jsonl(AGG_LOGS)
    metrics = [a for a in aggregates if a.get('endpoint') == endpoint]
    if window:
        metrics = [m for m in metrics if m.get('window_minutes') == window]
    return metrics

@app.post('/ingest')
async def ingest(log: LogEntry):
    record = log.dict()
    if not record.get('timestamp'):
        record['timestamp'] = datetime.utcnow().isoformat() + 'Z'
    try:
        with open(RAW_LOGS, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(record) + '\n')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to write log: {e}")
    return {"status": "ok"}

@app.get('/health')
async def health():
    return {"status": "ok"}
