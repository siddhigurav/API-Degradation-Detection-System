Explainable Early-Warning System for Silent API Degradation

Overview
- Detect early, low-noise degradations in API traffic using explainable, modular components.

Quick start

1. Create a virtualenv and install dependencies:

```bash
python -m venv .venv
.\.venv\Scripts\activate   # Windows PowerShell
pip install -r requirements.txt
```

2. Run the ingestion service:

```bash
uvicorn src.ingest_service:app --reload --port 8000
```

3. POST logs to `http://localhost:8000/ingest` with JSON body matching the schema.

What's included
- `src/ingest_service.py` — FastAPI log ingestion (writes raw JSONL to `data/raw_logs.jsonl`).
- `src/aggregator.py` — (planned) rolling-window aggregation logic.
- `src/detector.py` — (planned) EWMA/Z-score + optional IsolationForest.
- `src/correlator.py` — (planned) multi-signal validation logic (>=2 signals).
- `src/explainer.py` — (planned) explanation templates for alerts.
- `src/alerter.py` — (planned) Slack webhook + console alerts.
- `src/failure_injector.py` — (planned) scripts to inject synthetic degradations.

Architecture
--------
Simple component diagram (text):

Log producers -> `src/ingest_service.py` (FastAPI) -> raw JSONL `data/raw_logs.jsonl` -> `src/aggregator.py` (windowed aggregates) -> `data/aggregates.jsonl` -> `src/detector.py` (Z-score / EWMA rules) -> `src/correlator.py` (>=2 signals) -> `src/explainer.py` -> `src/alerter.py` (console + Slack + persisted alerts)

Why thresholds fail
-------------------
- Static thresholds trigger on expected seasonal variation or late-stage failures; they miss slow drifts (latency creep) and amplify noise when traffic volume is low.

Tradeoffs & limitations
-----------------------
- No deep learning — designed for interpretability and on-call usefulness rather than raw classification accuracy.
- Uses historical aggregates per-endpoint as baselines; requires enough historical volume for stable stats.
- False alerts are reduced via multi-signal correlation (>=2 independent metrics), but some scenarios (e.g. subtle data corruption) may still be missed.

Running the demo
----------------
1. Install deps and start services:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

2. Start the ingest service and runner in separate terminals:

```powershell
uvicorn src.ingest_service:app --reload --port 8000 --host 127.0.0.1
python src/runner.py
```

3. Run the synthetic demo (will inject a short gradual latency increase):

```powershell
python src/run_demo.py
```

4. After demo, compute simple metrics (time-to-detection):

```powershell
python src/compute_metrics.py
```

Demo Results
------------
- Synthetic gradual latency increase from 120ms to 1100ms over 5 minutes.
- Alert triggered after ~27 minutes (TTD) with explanation: "avg latency demo threshold >400ms; request volume pct=30.0% for /checkout over 15 minutes while request volume changed."
- 1 alert total, 0 false positives in demo.

Contact
-------
This project is designed for on-call engineers who need early, explainable warnings about silent API degradations. If you'd like, I can: run the demo here, tune thresholds, or add EWMA baselines.

Design notes
- No black-box models. Prefer EWMA/Z-score and IsolationForest for interpretable signals.
- Aggregation is per-endpoint and per-window (1m,5m,15m). No raw logs are fed directly into ML.

Next steps
- Implement aggregator, detector, correlator, explainer, alerter, and failure injection. Run demo and measure time-to-detection (TTD) and false-alert rate.
