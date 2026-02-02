API Degradation Detection System

Overview
- Framework for detecting early, low-noise degradations in API traffic using explainable, modular components.

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

Contact
- Designed for on-call engineers who need early, explainable warnings about silent API degradations.

Contributing
- Restore or extend `src/detector.py` to implement custom detection rules. Keep functions pure and testable.


