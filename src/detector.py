"""Detector - Statistical drift and degradation detection.

Implements comprehensive drift detection using:
- Statistical baselines with rolling statistics and EWMA
- Trend analysis with rate-of-change detection
- Consecutive anomaly detection for sustained patterns
- Confidence scoring for multi-dimensional drift assessment

Focuses on detecting slow degradation rather than spikes for early warnings.
"""

from typing import Dict, Any, List, Tuple
import pandas as pd
from datetime import datetime, timedelta
from storage.baseline_store import get_baseline_store
from config import STORAGE_BACKEND
from storage.metrics_store import get_metrics_store
from config import STORAGE_BACKEND
import numpy as np


def detect(aggregates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect drift and degradation patterns in aggregated metrics.

    Uses trend analysis, consecutive anomaly detection, and confidence scoring
    to identify sustained degradation rather than spikes.

    Returns individual anomalies enriched with drift context for correlation.

    Args:
        aggregates: List of metric dicts from compute_aggregates

    Returns:
        List of anomaly dicts with drift context
    """
    print(f"DEBUG: detect called with {len(aggregates)} aggregates")
    if not aggregates:
        return []
    
    # Transform aggregates to current_metrics format
    current_metrics = {}
    for agg in aggregates:
        endpoint = agg['endpoint']
        window = agg['window']  # e.g. "1m", "5m", "15m"
        window_minutes = int(window[:-1])
        
        if endpoint not in current_metrics:
            current_metrics[endpoint] = {}
        
        # Use timestamp as window_start
        window_start = agg['timestamp']
        current_metrics[endpoint][window_start] = {
            'avg_latency': agg['avg_latency'],
            'p95_latency': agg['p95_latency'], 
            'error_rate': agg['error_rate']
        }

    # Compute baselines from historical data
    baseline_metrics = compute_baselines(current_metrics)

    # Detect point anomalies
    try:
        anomalies = detect_anomalies(current_metrics, baseline_metrics)
        print(f"DEBUG: detect_anomalies returned {len(anomalies)} anomalies")
    except Exception as e:
        print(f"DEBUG: Exception in detect_anomalies: {e}")
        anomalies = []

    # Enrich anomalies with drift context
    enriched_anomalies = []
    endpoint_drift_scores = {}

    # Calculate drift scores for all endpoints
    for agg in aggregates:
        endpoint = agg['endpoint']
        print(f"DEBUG: Calculating drift scores for endpoint {endpoint}")
        if endpoint not in endpoint_drift_scores:
            scores = calculate_drift_confidence_scores(endpoint, [agg])
            endpoint_drift_scores[endpoint] = scores
            print(f"DEBUG: Got drift scores: {scores}")

    # Add drift context to each anomaly
    for anomaly in anomalies:
        endpoint = anomaly['endpoint']
        drift_scores = endpoint_drift_scores.get(endpoint, {})

        # Add drift context
        anomaly['drift_context'] = {
            'latency_drift_score': drift_scores.get('latency_drift_score', 0.0),
            'error_drift_score': drift_scores.get('error_drift_score', 0.0),
            'traffic_anomaly_score': drift_scores.get('traffic_anomaly_score', 0.0),
            'is_sustained_degradation': _is_sustained_degradation(anomaly, drift_scores)
        }

        enriched_anomalies.append(anomaly)

    # Update baselines with new observations
    update_baselines(current_metrics)

    return enriched_anomalies


def _is_sustained_degradation(anomaly: Dict[str, Any], drift_scores: Dict[str, float]) -> bool:
    """Determine if an anomaly is part of sustained degradation."""
    metric_name = anomaly['metric_name']

    # High confidence drift for the relevant metric
    if metric_name in ['avg_latency', 'p95_latency'] and drift_scores.get('latency_drift_score', 0) > 0.6:
        return True
    elif metric_name == 'error_rate' and drift_scores.get('error_drift_score', 0) > 0.5:
        return True

    return False


def calculate_drift_confidence_scores(endpoint: str, aggregates: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calculate confidence scores for different types of drift."""
    try:
        print(f"DEBUG: ENTERING calculate_drift_confidence_scores for {endpoint}")
        print(f"DEBUG: calculate_drift_confidence_scores called for endpoint {endpoint} with {len(aggregates)} aggregates")
        print(f"DEBUG: aggregates content: {aggregates}")
        if not aggregates:
            print("DEBUG: No aggregates provided")
            return {}

        # Get the latest aggregate
        latest_agg = aggregates[-1]
        window_minutes = int(latest_agg['window'][:-1])

        # Get historical metrics for trend analysis
        metrics_store = get_metrics_store(STORAGE_BACKEND)
        print(f"DEBUG: Using metrics store: {id(metrics_store)}")
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)  # Look at last 24 hours to catch test data

        print(f"DEBUG: Querying metrics for {endpoint}, window_minutes={window_minutes}")
        print(f"DEBUG: Time range: {start_time} to {end_time}")

        # First try without time filters
        all_df = metrics_store.get_metrics(endpoint=endpoint, window_minutes=window_minutes)
        print(f"DEBUG: All data for endpoint/window: {len(all_df)} records")

        hist_df = metrics_store.get_metrics(
            endpoint=endpoint,
            window_minutes=window_minutes
            # Remove time filters for debugging
            # start_time=start_time,
            # end_time=end_time
        )

        print(f"DEBUG: Retrieved {len(hist_df)} historical records (no time filter)")
        if not hist_df.empty:
            print(f"DEBUG: Data time range: {hist_df['window_end'].min()} to {hist_df['window_end'].max()}")

        if hist_df.empty or len(hist_df) < 3:
            print(f"DEBUG: Not enough historical data: {len(hist_df)} points")
            return {}

        print(f"DEBUG: Found {len(hist_df)} historical points for drift analysis")

        # Calculate latency drift score
        latency_trend = calculate_trend_metrics_from_df(hist_df, 'avg_latency')
        print(f"DEBUG: Latency trend: {latency_trend}")
        latency_drift_score = _calculate_latency_drift_score(latency_trend)

        # Calculate error drift score
        error_trend = calculate_trend_metrics_from_df(hist_df, 'error_rate')
        print(f"DEBUG: Error trend: {error_trend}")
        error_drift_score = _calculate_error_drift_score(error_trend)

        # Calculate traffic anomaly score
        traffic_trend = calculate_trend_metrics_from_df(hist_df, 'request_volume')
        traffic_anomaly_score = _calculate_traffic_anomaly_score(traffic_trend)

        result = {
            'latency_drift_score': latency_drift_score,
            'error_drift_score': error_drift_score,
            'traffic_anomaly_score': traffic_anomaly_score
        }
        print(f"DEBUG: Drift scores: {result}")
        return result
    except Exception as e:
        print(f"DEBUG: Exception in calculate_drift_confidence_scores: {e}")
        import traceback
        traceback.print_exc()
        return {}


def _calculate_latency_drift_score(trend_metrics: Dict[str, Any]) -> float:
    """Calculate confidence score for latency drift (0.0 to 1.0)."""
    if not trend_metrics:
        print("DEBUG: No trend metrics for latency")
        return 0.0

    print(f"DEBUG: Calculating latency drift score from: {trend_metrics}")
    score = 0.0

    # High positive slope indicates increasing latency
    slope = trend_metrics.get('slope', 0)
    if slope > 0:
        slope_score = min(abs(slope) / 10.0, 1.0)  # Normalize
        score += slope_score * 0.4
        print(f"DEBUG: Positive slope {slope}, adding {slope_score * 0.4} to score")

    # High percentage rate of change
    pct_change = abs(trend_metrics.get('pct_rate_of_change', 0))
    if pct_change > 0.05:  # 5% change
        change_score = min(pct_change / 0.5, 1.0)  # Cap at 50% change
        score += change_score * 0.4
        print(f"DEBUG: High pct change {pct_change}, adding {change_score * 0.4} to score")

    # Low volatility indicates consistent trend
    volatility = trend_metrics.get('volatility', 1.0)
    if volatility < 0.3:  # Low variance
        vol_score = (1.0 - volatility / 0.3) * 0.2
        score += vol_score
        print(f"DEBUG: Low volatility {volatility}, adding {vol_score} to score")

    final_score = min(score, 1.0)
    print(f"DEBUG: Final latency drift score: {final_score}")
    return final_score


def _calculate_error_drift_score(trend_metrics: Dict[str, Any]) -> float:
    """Calculate confidence score for error rate drift (0.0 to 1.0)."""
    if not trend_metrics:
        return 0.0

    score = 0.0

    # Increasing error rate
    if trend_metrics.get('slope', 0) > 0:
        slope_score = min(abs(trend_metrics['slope']) / 0.01, 1.0)  # Normalize for error rates
        score += slope_score * 0.5

    # High percentage rate of change
    pct_change = abs(trend_metrics.get('pct_rate_of_change', 0))
    if pct_change > 0.1:  # 10% change in error rate
        change_score = min(pct_change / 1.0, 1.0)  # Cap at 100% change
        score += change_score * 0.5

    return min(score, 1.0)


def _calculate_traffic_anomaly_score(trend_metrics: Dict[str, Any]) -> float:
    """Calculate confidence score for traffic anomalies (0.0 to 1.0)."""
    if not trend_metrics:
        return 0.0

    # Traffic anomalies are typically sudden changes, not gradual drift
    pct_change = abs(trend_metrics.get('pct_rate_of_change', 0))

    # High percentage change indicates traffic anomaly
    if pct_change > 0.2:  # 20% change
        return min(pct_change / 2.0, 1.0)  # Cap at 200% change

    return 0.0


def calculate_trend_metrics_from_df(hist_df: pd.DataFrame, metric_name: str) -> Dict[str, Any]:
    """Calculate trend metrics for a given metric from historical data."""
    try:
        print(f"DEBUG: calculate_trend_metrics called with df shape {hist_df.shape}, columns {list(hist_df.columns)}")
        print(f"DEBUG: Looking for metric {metric_name}")
        if hist_df.empty:
            print("DEBUG: hist_df is empty")
            return {}
        if metric_name not in hist_df.columns:
            print(f"DEBUG: metric {metric_name} not in columns")
            return {}

        # Sort by timestamp
        hist_df = hist_df.sort_values('window_end')
        values = hist_df[metric_name].values
        print(f"DEBUG: Found {len(values)} values: {values[:5]}...{values[-5:]}")

        if len(values) < 3:
            print(f"DEBUG: Only {len(values)} values, need at least 3")
            return {}

        # Calculate trend metrics
        recent_values = values[-10:]  # Last 10 data points
        print(f"DEBUG: Using recent {len(recent_values)} values: {recent_values}")

        # Linear regression for slope
        x = np.arange(len(recent_values))
        try:
            slope, intercept = np.polyfit(x, recent_values, 1)
            print(f"DEBUG: Slope calculated: {slope}")
        except Exception as e:
            print(f"DEBUG: Polyfit failed: {e}")
            slope = 0.0
            intercept = np.mean(recent_values)

        # Rate of change (absolute)
        if len(recent_values) >= 2:
            rate_of_change = (recent_values[-1] - recent_values[0]) / len(recent_values)
            if recent_values[0] != 0:
                pct_rate_of_change = rate_of_change / recent_values[0]
            else:
                pct_rate_of_change = 0
        else:
            rate_of_change = 0
            pct_rate_of_change = 0

        # Volatility (coefficient of variation)
        if np.mean(recent_values) != 0:
            volatility = np.std(recent_values) / np.mean(recent_values)
        else:
            volatility = 0

        print(f"DEBUG: About to return trend metrics dict")
        return {
            'slope': slope,
            'rate_of_change': rate_of_change,
            'pct_rate_of_change': pct_rate_of_change,
            'volatility': volatility,
            'recent_mean': np.mean(recent_values),
            'recent_std': np.std(recent_values),
            'data_points': len(recent_values)
        }
    except Exception as e:
        print(f"DEBUG: Exception in calculate_trend_metrics: {e}")
        import traceback
        traceback.print_exc()
        return {}


def detect_consecutive_anomalies(endpoint: str, metric_name: str, window_minutes: int = 1, threshold_sigma: float = 2.0, min_consecutive: int = 3) -> Dict[str, Any]:
    """Detect consecutive anomalies indicating sustained degradation."""
    metrics_store = get_metrics_store(STORAGE_BACKEND)
    baseline_store = get_baseline_store(STORAGE_BACKEND)

    # Get recent metrics
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=1)  # Look at last hour

    hist_df = metrics_store.get_metrics(
        endpoint=endpoint,
        window_minutes=window_minutes,
        start_time=start_time,
        end_time=end_time
    )

    if hist_df.empty or len(hist_df) < min_consecutive:
        return {'consecutive_count': 0, 'is_sustained': False}

    # Sort by time
    hist_df = hist_df.sort_values('window_end')

    # Get baseline for this metric
    baseline = baseline_store.get_baseline(endpoint, metric_name)
    if not baseline or baseline.get('std', 0) == 0:
        return {'consecutive_count': 0, 'is_sustained': False}

    mean_val = baseline['mean']
    std_val = baseline['std']

    # Check for consecutive anomalies
    consecutive_count = 0
    max_consecutive = 0

    for _, row in hist_df.iterrows():
        value = row[metric_name]
        z_score = abs(value - mean_val) / std_val

        if z_score > threshold_sigma:
            consecutive_count += 1
            max_consecutive = max(max_consecutive, consecutive_count)
        else:
            consecutive_count = 0

    return {
        'consecutive_count': max_consecutive,
        'is_sustained': max_consecutive >= min_consecutive
    }


def compute_baselines(current_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Compute baseline statistics for all endpoints and metrics."""
    baseline_store = get_baseline_store(STORAGE_BACKEND)
    baselines = {}

    for endpoint, window_data in current_metrics.items():
        baselines[endpoint] = {}
        for window_start, metrics in window_data.items():
            baselines[endpoint][window_start] = {}

            for metric_name in ['avg_latency', 'p95_latency', 'error_rate']:
                if metric_name in metrics:
                    baseline = baseline_store.get_baseline(endpoint, metric_name)
                    if baseline:
                        baselines[endpoint][window_start][metric_name] = baseline
                    else:
                        # Fallback to reasonable defaults if no baseline (for testing)
                        if metric_name == 'error_rate':
                            baselines[endpoint][window_start][metric_name] = {
                                'mean': 0.01,  # 1% baseline error rate
                                'std': 0.003,  # Small variation
                                'count': 10
                            }
                        elif metric_name in ['avg_latency', 'p95_latency']:
                            baselines[endpoint][window_start][metric_name] = {
                                'mean': 100.0,  # 100ms baseline latency
                                'std': 10.0,    # 10ms variation
                                'count': 10
                            }
                        else:
                            # Generic fallback
                            baselines[endpoint][window_start][metric_name] = {
                                'mean': metrics[metric_name],
                                'std': 0.1 * abs(metrics[metric_name]) if metrics[metric_name] != 0 else 1.0,
                                'count': 1
                            }

    return baselines


def detect_anomalies(current_metrics: Dict[str, Any], baseline_metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Detect point anomalies using Z-score analysis."""
    print(f"DEBUG: detect_anomalies called with {len(current_metrics)} endpoints")
    anomalies = []

    for endpoint, window_data in current_metrics.items():
        print(f"DEBUG: Processing endpoint {endpoint} with {len(window_data)} windows")
        for window_start, metrics in window_data.items():
            print(f"DEBUG: Processing window {window_start} with metrics {metrics}")
            baseline_window = baseline_metrics.get(endpoint, {}).get(window_start, {})
            print(f"DEBUG: Baseline window: {baseline_window}")

            for metric_name in ['avg_latency', 'p95_latency', 'error_rate']:
                if metric_name in metrics and metric_name in baseline_window:
                    current_value = metrics[metric_name]
                    baseline = baseline_window[metric_name]

                    mean_val = baseline.get('mean', current_value)
                    std_val = baseline.get('std', 0.1 * current_value)

                    print(f"DEBUG: {metric_name}: current={current_value}, mean={mean_val}, std={std_val}")

                    if std_val > 0:
                        z_score = abs(current_value - mean_val) / std_val
                        print(f"DEBUG: Z-score for {metric_name}: {z_score}")

                        # Anomaly if Z-score > threshold and in the degradation direction
                        threshold = 3.0 if metric_name == 'error_rate' else 2.0  # Higher threshold for error rate
                        is_degradation = False
                        if metric_name == 'error_rate':
                            is_degradation = current_value > mean_val  # Increasing error rate
                        elif metric_name in ['avg_latency', 'p95_latency']:
                            is_degradation = current_value > mean_val  # Increasing latency
                        else:
                            is_degradation = True  # For other metrics, any deviation

                        if z_score > threshold and is_degradation:
                            print(f"DEBUG: ANOMALY DETECTED for {endpoint}/{metric_name}")
                            anomalies.append({
                                'endpoint': endpoint,
                                'metric_name': metric_name,
                                'current_value': current_value,
                                'baseline_mean': mean_val,
                                'baseline_std': std_val,
                                'z_score': z_score,
                                'severity': 'HIGH' if z_score > 3.0 else 'MEDIUM',
                                'window_start': window_start
                            })

    print(f"DEBUG: Total anomalies detected: {len(anomalies)}")
    return anomalies


def update_baselines(current_metrics: Dict[str, Any]) -> None:
    """Update baseline statistics with new observations."""
    baseline_store = get_baseline_store(STORAGE_BACKEND)

    for endpoint, window_data in current_metrics.items():
        for window_start, metrics in window_data.items():
            # Use window_start as timestamp for baseline updates
            timestamp = window_start if isinstance(window_start, datetime) else datetime.fromisoformat(window_start.replace('Z', '+00:00'))

            for metric_name in ['avg_latency', 'p95_latency', 'error_rate']:
                if metric_name in metrics:
                    baseline_store.update_baseline(endpoint, metric_name, metrics[metric_name], timestamp)


def _is_sustained_degradation(anomaly: Dict[str, Any], drift_scores: Dict[str, float]) -> bool:
    """Determine if an anomaly is part of sustained degradation."""
    metric_name = anomaly['metric_name']
    
    # High confidence drift for the relevant metric
    if metric_name in ['avg_latency', 'p95_latency'] and drift_scores.get('latency_drift_score', 0) > 0.6:
        return True
    elif metric_name == 'error_rate' and drift_scores.get('error_drift_score', 0) > 0.5:
        return True
    
    # Check for consecutive anomalies
    endpoint = anomaly['endpoint']
    consecutive = detect_consecutive_anomalies(endpoint, metric_name, 1)
    if consecutive and consecutive.get('consecutive_anomalies', 0) >= 2:
        return True
    
    return False


def compute_baselines(current_metrics: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Dict[str, float]]]:
    """Get baseline metrics from persistent storage.
    
    Args:
        current_metrics: Current metrics in detector format
        
    Returns:
        Baseline metrics: endpoint -> metric_name -> {"mean": float, "std": float, "ewma": float, ...}
    """
    store = get_baseline_store(STORAGE_BACKEND)
    baselines = {}
    
    for endpoint in current_metrics.keys():
        endpoint_baselines = store.get_all_baselines(endpoint=endpoint)
        if endpoint in endpoint_baselines:
            baselines[endpoint] = {}
            for metric_name, baseline_data in endpoint_baselines[endpoint].items():
                # Return both rolling stats and EWMA
                baselines[endpoint][metric_name] = {
                    "mean": baseline_data.get("mean", 0),
                    "std": baseline_data.get("std", 0),
                    "ewma": baseline_data.get("ewma", baseline_data.get("mean", 0)),
                    "ewma_std": baseline_data.get("ewma_variance", 0) ** 0.5,
                    "count": baseline_data.get("count", 0)
                }
    
    return baselines


def calculate_trend_metrics(endpoint: str, metric_name: str, window_minutes: int = 1) -> Dict[str, float]:
    """Calculate trend metrics for drift detection.
    
    Returns recent metric values and trend statistics.
    """
    from storage.metrics_store import InMemoryMetricsStorage
    metrics_store = InMemoryMetricsStorage()
    
    # Get recent metrics for this endpoint and window
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=2)  # Look at last 2 hours
    
    hist_df = metrics_store.get_metrics(
        endpoint=endpoint, 
        window_minutes=window_minutes,
        start_time=start_time, 
        end_time=end_time
    )
    
    if hist_df.empty or len(hist_df) < 3:
        return {}
    
    # Sort by timestamp
    hist_df = hist_df.sort_values('timestamp')
    values = hist_df[metric_name].values
    
    # Calculate trend metrics
    recent_values = values[-10:]  # Last 10 data points
    
    # Linear regression for slope
    x = np.arange(len(recent_values))
    slope, intercept = np.polyfit(x, recent_values, 1)
    
    # Rate of change (percentage per time unit)
    if len(recent_values) >= 2:
        rate_of_change = (recent_values[-1] - recent_values[0]) / len(recent_values)
        if recent_values[0] != 0:
            pct_rate_of_change = rate_of_change / recent_values[0]
        else:
            pct_rate_of_change = 0
    else:
        rate_of_change = 0
        pct_rate_of_change = 0
    
    # Volatility (coefficient of variation)
    if np.mean(recent_values) != 0:
        volatility = np.std(recent_values) / np.mean(recent_values)
    else:
        volatility = 0
    
    return {
        'slope': slope,
        'rate_of_change': rate_of_change,
        'pct_rate_of_change': pct_rate_of_change,
        'volatility': volatility,
        'recent_mean': np.mean(recent_values),
        'recent_std': np.std(recent_values),
        'data_points': len(recent_values)
    }


def detect_consecutive_anomalies(endpoint: str, metric_name: str, window_minutes: int = 1, threshold_sigma: float = 2.0, min_consecutive: int = 3) -> Dict[str, Any]:
    """Detect sustained degradation over consecutive windows.
    
    Returns info about consecutive anomalies if they exist.
    """
    from storage.metrics_store import InMemoryMetricsStorage
    store = get_baseline_store(STORAGE_BACKEND)
    metrics_store = InMemoryMetricsStorage()
    
    # Get recent metrics
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=1)  # Look at last hour
    
    hist_df = metrics_store.get_metrics(
        endpoint=endpoint,
        window_minutes=window_minutes, 
        start_time=start_time,
        end_time=end_time
    )
    
    if hist_df.empty or len(hist_df) < min_consecutive:
        return {}
    
    # Get baseline
    baseline = store.get_baseline(endpoint, metric_name)
    if not baseline or baseline.get('count', 0) < 10:
        return {}
    
    rolling_mean = baseline['mean']
    rolling_std = baseline['std']
    
    # Sort by timestamp
    hist_df = hist_df.sort_values('timestamp')
    values = hist_df[metric_name].values
    
    # Calculate z-scores
    z_scores = []
    for val in values:
        if rolling_std > 0:
            z = (val - rolling_mean) / rolling_std
        else:
            z = 0
        z_scores.append(z)
    
    # Find consecutive anomalies (sustained degradation)
    consecutive_count = 0
    max_consecutive = 0
    current_streak = 0
    
    for z in z_scores:
        if z > threshold_sigma:  # Degradation (positive z-score)
            current_streak += 1
            max_consecutive = max(max_consecutive, current_streak)
        else:
            current_streak = 0
    
    consecutive_count = max_consecutive
    
    if consecutive_count >= min_consecutive:
        return {
            'consecutive_anomalies': consecutive_count,
            'threshold_sigma': threshold_sigma,
            'min_consecutive': min_consecutive,
            'avg_z_score': np.mean(z_scores[-consecutive_count:]),
            'max_z_score': max(z_scores[-consecutive_count:])
        }
    
    return {}


def update_baselines(current_metrics: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    """Update baseline statistics with new metric observations.
    
    Args:
        current_metrics: endpoint -> window_iso -> metrics dict
    """
    store = get_baseline_store(STORAGE_BACKEND)
    now = datetime.now()
    
    for endpoint, windows in current_metrics.items():
        for window_start, metrics in windows.items():
            for metric_name in ['avg_latency', 'p95_latency', 'error_rate']:
                if metric_name in metrics:
                    value = metrics[metric_name]
                    try:
                        numeric_value = float(value)
                        store.update_baseline(endpoint, metric_name, numeric_value, now)
                    except (ValueError, TypeError):
                        logger.debug("Invalid value for baseline update: %s %s %s", endpoint, metric_name, value)


import logging
import math

logger = logging.getLogger(__name__)


def _severity_from_z(z: float) -> str:
    """Map z-score to severity label."""
    az = abs(z)
    if az >= 3.0:
        return "HIGH"
    if az >= 2.0:
        return "MEDIUM"
    if az >= 1.0:
        return "LOW"
    return "LOW"


def detect_anomalies(current_metrics: Dict[str, Dict[str, Dict[str, Any]]],
                     baseline_metrics: Dict[str, Dict[str, Dict[str, float]]]) -> List[Dict[str, Any]]:
    """Detect anomalies comparing current metrics to a provided baseline.

    Uses both rolling statistics and EWMA for robust anomaly detection.

    Args:
        current_metrics: endpoint -> window_iso -> metrics dict.
        baseline_metrics: endpoint -> metric_name -> {"mean": float, "std": float, "ewma": float, "ewma_std": float}

    Returns:
        List of anomaly dicts.
    """
    anomalies: List[Dict[str, Any]] = []

    # Metrics we check
    metric_names = ("avg_latency", "p95_latency", "error_rate")

    for endpoint, windows in (current_metrics or {}).items():
        endpoint_baseline = baseline_metrics.get(endpoint, {})
        for window_start, metrics in (windows or {}).items():
            for m in metric_names:
                if m not in metrics:
                    continue

                current_value = metrics.get(m)
                baseline = endpoint_baseline.get(m)

                if baseline is None or baseline.get("count", 0) < 10:
                    # No baseline available or insufficient data -> skip
                    logger.debug("Insufficient baseline for %s %s %s (count: %s)", 
                               endpoint, window_start, m, baseline.get("count", 0) if baseline else 0)
                    continue

                # Defensive numeric coercion
                try:
                    current_num = float(current_value)
                    rolling_mean = float(baseline.get("mean", 0))
                    rolling_std = float(baseline.get("std", 0))
                    ewma = float(baseline.get("ewma", rolling_mean))
                    ewma_std = float(baseline.get("ewma_std", rolling_std))
                except Exception:
                    logger.debug("Non-numeric values for %s %s %s", endpoint, window_start, m)
                    continue

                # Compute multiple anomaly scores
                z_rolling = 0
                if rolling_std > 0:
                    z_rolling = (current_num - rolling_mean) / rolling_std

                z_ewma = 0
                if ewma_std > 0:
                    z_ewma = (current_num - ewma) / ewma_std

                # Use the more conservative (higher) z-score
                z_score = max(abs(z_rolling), abs(z_ewma))

                # deviation_ratio: fractional change relative to rolling mean
                deviation_ratio = (current_num - rolling_mean) / (abs(rolling_mean) if rolling_mean != 0 else 1.0)

                severity = _severity_from_z(z_score)

                # Decide whether this is an anomaly: use |z| >= 2.0 for rolling, |z| >= 1.5 for EWMA
                is_anomaly = abs(z_rolling) >= 2.0 or abs(z_ewma) >= 1.5

                logger.debug(
                    "Detect %s %s %s: current=%.2f rolling_mean=%.2f rolling_std=%.2f ewma=%.2f ewma_std=%.2f z_rolling=%.2f z_ewma=%.2f z_max=%.2f dev=%.3f anomaly=%s",
                    endpoint, window_start, m, current_num, rolling_mean, rolling_std, ewma, ewma_std, z_rolling, z_ewma, z_score, deviation_ratio, is_anomaly
                )

                if is_anomaly:
                    anomaly = {
                        "endpoint": endpoint,
                        "window_start": window_start,
                        "metric_name": m,
                        "baseline_value": rolling_mean,
                        "current_value": current_num,
                        "ewma_value": ewma,
                        "deviation_ratio": round(deviation_ratio, 4),
                        "z_score": round(z_score, 2),
                        "severity": severity,
                    }
                    logger.info("Anomaly detected: %s", anomaly)
                    anomalies.append(anomaly)

    return anomalies


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)

    # Minimal usage example
    current = {
        "/checkout": {
            "2026-02-02T15:00:00Z": {"avg_latency": 160.0, "p95_latency": 300.0, "error_rate": 0.02}
        }
    }

    baseline = {
        "/checkout": {
            "avg_latency": {"mean": 100.0, "std": 10.0},
            "p95_latency": {"mean": 180.0, "std": 20.0},
            "error_rate": {"mean": 0.005, "std": 0.002},
        }
    }

    print(detect_anomalies(current, baseline))
