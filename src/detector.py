"""
Explainable Anomaly Detection Module

Uses EWMA (for slow drifts) and Z-Score (for sudden spikes) per endpoint.
Trains on historical aggregates per metric.
Detects deviations with configurable thresholds.
Justification: reasons include z-score, pct-change, ewma-deviation.

Threshold Logic:
- Z-Score > 3.0: Sudden spike/outlier.
- Pct Change > 25%: Significant change.
- EWMA Deviation > 0.2: Slow drift (current - ewma_mean) / ewma_std > 0.2.
- Demo threshold: avg_latency > 400ms for testing.

Example Input: List of new aggregates (from aggregator).
Example Output: Dict of detections with flagged metrics and reasons.
"""

import os
import json
import math
import pandas as pd
from typing import Dict, Any, List

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'data'))
AGG_LOGS = os.path.join(DATA_DIR, 'aggregates.jsonl')

# Configurable thresholds (engineer-tunable)
Z_SCORE_THRESHOLD = 3.0
PCT_CHANGE_THRESHOLD = 0.25  # 25% change flagged
EWMA_DEVIATION_THRESHOLD = 0.2  # Deviation from EWMA mean in std units
MIN_VOLUME_FOR_STATS = 5


def read_aggregates():
    if not os.path.exists(AGG_LOGS):
        return pd.DataFrame()
    records = []
    with open(AGG_LOGS, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df['window_end'] = pd.to_datetime(df['window_end'])
    return df


def detect(aggregates: List[Dict[str, Any]]):
    """
    Input: newest aggregate records (list of per-endpoint dicts for one run)
    Output: detections: dict endpoint -> list of metric detections
    Each detection: {metric, value, baseline_mean, baseline_std, z_score, pct_change, ewma_mean, ewma_std, ewma_dev, flagged, reasons}
    """
    detections = {}
    if not aggregates:
        return detections
    df_all = read_aggregates()
    df_new = pd.DataFrame(aggregates)
    for _, row in df_new.iterrows():
        endpoint = row['endpoint']
        w = row['window_minutes']
        # build baseline from historical aggregates for same endpoint and window size
        mask = (df_all['endpoint'] == endpoint) & (df_all['window_minutes'] == w)
        hist = df_all[mask]
        endpoint_dets = []
        for metric in ['avg_latency', 'p95_latency', 'error_rate', 'request_volume', 'response_size_variance']:
            cur = float(row.get(metric, float('nan')))
            baseline_mean = float(hist[metric].mean()) if not hist.empty else float('nan')
            baseline_std = float(hist[metric].std(ddof=0)) if not hist.empty else float('nan')
            # Compute z-score
            if not math.isnan(baseline_std) and baseline_std > 0:
                z = (cur - baseline_mean) / baseline_std
            else:
                z = float('nan')
            pct_change = (cur - baseline_mean) / baseline_mean if (baseline_mean and not math.isnan(baseline_mean)) else float('nan')
            # Compute EWMA for drift detection
            ewma_mean = float('nan')
            ewma_std = float('nan')
            ewma_dev = float('nan')
            if not hist.empty and len(hist) > 1:
                # Sort by time for EWMA
                hist_sorted = hist.sort_values('window_end')
                ewma_series = hist_sorted[metric].ewm(span=10).mean()  # span=10 for smoothing
                ewma_mean = ewma_series.iloc[-1]  # Latest EWMA
                ewma_std = hist_sorted[metric].ewm(span=10).std().iloc[-1] if len(hist_sorted) > 1 else 0.0
                if not math.isnan(ewma_std) and ewma_std > 0:
                    ewma_dev = (cur - ewma_mean) / ewma_std
            flagged = False
            reasons = []
            if not math.isnan(z) and abs(z) >= Z_SCORE_THRESHOLD:
                flagged = True
                reasons.append(f'z={z:.2f}')
            if not math.isnan(pct_change) and abs(pct_change) >= PCT_CHANGE_THRESHOLD:
                flagged = True
                reasons.append(f'pct={pct_change*100:.1f}%')
            if not math.isnan(ewma_dev) and abs(ewma_dev) >= EWMA_DEVIATION_THRESHOLD:
                flagged = True
                reasons.append(f'ewma_dev={ewma_dev:.2f}')
            # Demo: simple threshold for avg_latency
            if metric == 'avg_latency' and cur > 400:
                flagged = True
                reasons.append('demo threshold >400ms')
            # volume safeguard
            vol_ok = True
            if 'request_volume' in hist.columns and len(hist) < MIN_VOLUME_FOR_STATS:
                vol_ok = False
            det = {
                'metric': metric,
                'value': cur,
                'baseline_mean': baseline_mean,
                'baseline_std': baseline_std,
                'z_score': z,
                'pct_change': pct_change,
                'ewma_mean': ewma_mean,
                'ewma_std': ewma_std,
                'ewma_dev': ewma_dev,
                'flagged': flagged and vol_ok,
                'reasons': reasons,
                'window_minutes': w,
            }
            endpoint_dets.append(det)
        if endpoint_dets:
            detections.setdefault(endpoint, []).extend(endpoint_dets)
    return detections


if __name__ == '__main__':
    print('Detector dry-run: reading latest aggregates...')
    # To run a manual detection pass, generate aggregates then call `detect()` with the new records.
