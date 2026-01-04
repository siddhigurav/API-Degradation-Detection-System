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
from aggregator import read_aggregates as read_agg_from_storage
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
    """Read historical aggregates from storage (SQLite or JSONL)."""
    df = read_agg_from_storage()
    # Ensure we have the expected column format for detector
    if 'window' in df.columns and 'window_minutes' not in df.columns:
        df['window_minutes'] = df['window'].str.rstrip('m').astype(int)
    if 'response_var' in df.columns and 'response_size_variance' not in df.columns:
        df['response_size_variance'] = df['response_var']
    if 'timestamp' in df.columns and 'window_end' not in df.columns:
        df['window_end'] = pd.to_datetime(df['timestamp'], format='mixed')
    return df
    df['window_end'] = pd.to_datetime(df['window_end'])
    return df


def detect(aggregates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Input: newest aggregate records (list of per-endpoint dicts for one run)
    Output: List of metric-level anomalies with simplified format
    Each anomaly: {metric, deviation, window, severity}
    """
    anomalies = []
    if not aggregates:
        return anomalies

    df_all = read_aggregates()
    df_new = pd.DataFrame(aggregates)

    # Convert window format if needed
    if 'window' in df_new.columns:
        df_new['window_minutes'] = df_new['window'].str.rstrip('m').astype(int)
    if 'response_var' in df_new.columns:
        df_new['response_size_variance'] = df_new['response_var']

    for _, row in df_new.iterrows():
        endpoint = row['endpoint']
        w = row['window_minutes']
        window_str = f"{w}m"

        # Build baseline from historical aggregates for same endpoint and window size
        mask = (df_all['endpoint'] == endpoint) & (df_all['window_minutes'] == w)
        hist = df_all[mask]

        for metric in ['avg_latency', 'p95_latency', 'error_rate', 'request_volume', 'response_size_variance']:
            cur = float(row.get(metric, float('nan')))
            if math.isnan(cur):
                continue

            baseline_mean = float(hist[metric].mean()) if not hist.empty else float('nan')
            baseline_std = float(hist[metric].std(ddof=0)) if not hist.empty else float('nan')

            # Skip if insufficient historical data
            if hist.empty or len(hist) < MIN_VOLUME_FOR_STATS:
                continue

            # Calculate deviation (normalized z-score)
            deviation = float('nan')
            if not math.isnan(baseline_std) and baseline_std > 0:
                deviation = (cur - baseline_mean) / baseline_std

            # Determine severity based on deviation magnitude
            severity = "LOW"
            if not math.isnan(deviation):
                if abs(deviation) >= 5.0:
                    severity = "CRITICAL"
                elif abs(deviation) >= 3.0:
                    severity = "HIGH"
                elif abs(deviation) >= 2.0:
                    severity = "MEDIUM"

            # Check for anomalies using multiple methods
            is_anomaly = False

            # Z-score method (sudden spikes)
            if not math.isnan(deviation) and abs(deviation) >= Z_SCORE_THRESHOLD:
                is_anomaly = True

            # Percentage change method
            pct_change = (cur - baseline_mean) / baseline_mean if (baseline_mean and not math.isnan(baseline_mean) and baseline_mean != 0) else float('nan')
            if not math.isnan(pct_change) and abs(pct_change) >= PCT_CHANGE_THRESHOLD:
                is_anomaly = True

            # EWMA drift detection
            if len(hist) > 1:
                hist_sorted = hist.sort_values('window_end')
                ewma_series = hist_sorted[metric].ewm(span=10).mean()
                ewma_mean = ewma_series.iloc[-1]
                ewma_std = hist_sorted[metric].ewm(span=10).std().iloc[-1] if len(hist_sorted) > 1 else 0.0

                if not math.isnan(ewma_std) and ewma_std > 0:
                    ewma_dev = (cur - ewma_mean) / ewma_std
                    if abs(ewma_dev) >= EWMA_DEVIATION_THRESHOLD:
                        is_anomaly = True

            # Create anomaly record if detected
            if is_anomaly:
                anomaly = {
                    'metric': metric,
                    'deviation': round(deviation, 2) if not math.isnan(deviation) else 0.0,
                    'window': window_str,
                    'severity': severity,
                    'endpoint': endpoint,  # Include endpoint for context
                    'current_value': cur,
                    'baseline_mean': baseline_mean
                }
                anomalies.append(anomaly)

    return anomalies


if __name__ == '__main__':
    print('Detector dry-run: reading latest aggregates...')
    # To run a manual detection pass, generate aggregates then call `detect()` with the new records.
