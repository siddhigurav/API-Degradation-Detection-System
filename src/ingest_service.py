from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import os
import json
from datetime import datetime

app = FastAPI(title="EWS Ingest Service")

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'data'))
RAW_LOGS = os.path.join(DATA_DIR, 'raw_logs.jsonl')

os.makedirs(DATA_DIR, exist_ok=True)

class LogEntry(BaseModel):
    timestamp: Optional[str] = Field(None, description="ISO8601 timestamp. If omitted server time will be used.")
    endpoint: str
    status_code: int
    latency_ms: float
    response_size: int
    error_message: Optional[str] = None

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
