API Degradation Detection System

## Overview
Framework for detecting early, low-noise degradations in API traffic using explainable, modular components with scalable storage backends.

## Storage Architecture: From Files to Databases

This system implements a **phased storage upgrade path** that scales from development to enterprise production:

### Phase 1: In-Memory (MVP/Development)
```bash
# Default: fast, no persistence, perfect for development
STORAGE_BACKEND=memory python demo_alerting.py
```
- **Use case**: Development, testing, demos
- **Pros**: Fastest, no setup, zero persistence
- **Cons**: Data lost on restart, limited capacity

### Phase 2: SQLite (Production Default)
```bash
# Production-ready persistence with SQL
STORAGE_BACKEND=sqlite SQLITE_DB_PATH=data/alerts.db python demo_alerting.py
```
- **Use case**: Single-server production, small teams
- **Pros**: ACID transactions, SQL queries, file-based, zero config
- **Cons**: Single-writer limitation, filesystem coupling

### Phase 3: Redis (High-Performance State)
```bash
# High-throughput caching and state sharing
STORAGE_BACKEND=redis REDIS_URL=redis://localhost:6379/0 python demo_alerting.py
```
- **Use case**: High-throughput, distributed services, fast state sharing
- **Pros**: Sub-millisecond access, pub/sub, automatic expiration
- **Cons**: Requires Redis server, no complex queries

### Phase 4: TimescaleDB (Time-Series Analytics)
```bash
# Advanced time-series analytics and historical analysis
STORAGE_BACKEND=timescale TIMESCALE_CONNECTION_STRING=postgresql://localhost:5432/alerts python demo_alerting.py
```
- **Use case**: Enterprise analytics, backtesting, long-term retention
- **Pros**: Time-series optimized, advanced analytics, PostgreSQL ecosystem
- **Cons**: Requires PostgreSQL + TimescaleDB setup

### Configuration

Set storage backend via environment variables:

```bash
# Storage Backend Selection
STORAGE_BACKEND=memory|sqlite|redis|timescale

# SQLite Configuration
SQLITE_DB_PATH=data/alerts.db

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
REDIS_KEY_PREFIX=alerts:

# TimescaleDB Configuration
TIMESCALE_CONNECTION_STRING=postgresql://user:pass@localhost:5432/alerts
```

### Benefits of This Architecture

✅ **Real Data Retention** - No more lost alerts on restart
✅ **Backtesting Capabilities** - Historical data for algorithm improvement
✅ **Scalability** - From single developer to enterprise deployment
✅ **Flexibility** - Switch backends without code changes
✅ **Performance** - Choose the right tool for your scale

## Quick Start

Quick start

1. Create a virtualenv and install dependencies:

```bash
python -m venv .venv
.\.venv\Scripts\activate   # Windows PowerShell
pip install -r requirements.txt
```

2. Run the ingestion service (default port 8000):

```bash
uvicorn src.ingest_service:app --reload --port 8000
```

3. Send logs to the ingest endpoint. The demo failure injector posts to `/ingest` and can be pointed at any base URL.

```bash
# Example: run the injector for 5 minutes against local ingest service
python src/failure_injector.py --duration 5 --url http://localhost:8000
```

What's included
- `src/ingest_service.py` — FastAPI log ingestion (writes raw JSONL to `data/raw_logs.jsonl`).
- `src/aggregator.py` — Rolling-window aggregation logic.
- `src/detector.py` — Lightweight stub (placeholder). Replace with detection logic if needed.
- `src/detector_old.py` — Legacy stub (kept as minimal shim).
- `src/correlator.py` — Multi-signal validation logic (>=2 signals).
- `src/explainer.py` — Explanation templates and `explain_alerts()` helper.
- `src/alerter.py` — Slack webhook + console alerts.
- `src/failure_injector.py` — Runnable demo script that simulates traffic, gradually increases latency, and slowly introduces errors.

Recent changes
- Added `src/failure_injector.py`: a demo-only simulator that sends synthetic logs to the ingest API, with configurable duration and target URL.
- Replaced heavy legacy detectors with safe stubs (`src/detector.py`, `src/detector_old.py`) to simplify the demo flow. If you need the full detector implementation, restore from git history or implement detection logic in `src/detector.py`.

Failure injector (demo)
- Purpose: simulate API traffic, gradually introduce latency and errors, send logs to `/ingest`.
- Usage example (5 minutes against local ingest service):

```bash
python src/failure_injector.py --duration 5 --url http://localhost:8000
```

Options:
- `--duration`: minutes to run (default 10)
- `--url`: base URL for the API (default http://localhost:8001 in the script; override via `--url`)

Notes & limitations
- The failure injector is for demos only — it uses `requests`, `random`, and `time.sleep` and posts real HTTP requests to the configured ingest endpoint.
- Detector modules are currently stubs to avoid heavy legacy code during demos; reinstate or implement real detection logic before relying on production alerts.

Testing
- Quick syntax check: `python -m py_compile src/*.py`
- Run the test suite with `pytest` if available.

## Demo Data

Generate sample metrics and alerts to demonstrate the dashboard functionality:

```bash
# Generate demo data (24 hours of metrics + sample alerts)
python demo_data.py
```

This creates realistic API traffic patterns with gradual degradation in the last few hours.

## Dashboard

A minimal web dashboard for visualizing API health, drift timelines, and alert history:

```bash
# Install dependencies
pip install -r requirements.txt

# Generate demo data (if not already done)
python demo_data.py

# Run the dashboard
python dashboard.py
```

Then open http://localhost:5000 in your browser.

**Features:**
- **Endpoint Health Scores**: Real-time health metrics (0-100) for all endpoints
- **Drift Timelines**: Matplotlib plots showing latency and error rate trends over time
- **Alert History**: Recent alerts with explanations, insights, and recommendations
- **Interactive Controls**: Filter by endpoint and time range

Contact
- Designed for on-call engineers who need early, explainable warnings about silent API degradations.

Contributing
- Restore or extend `src/detector.py` to implement custom detection rules. Keep functions pure and testable.


