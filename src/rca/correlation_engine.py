"""
Correlation Analysis Engine

Computes and analyzes metric correlations during anomalies.
Uses rolling window statistics to detect correlated metrics.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from scipy import stats
import structlog

from src.rca.models import (
    MetricCorrelation, CorrelationSnapshot, CorrelationType
)

log = structlog.get_logger()


class CorrelationEngine:
    """Analyzes metric correlations"""
    
    # Correlation thresholds for classification
    CORRELATION_THRESHOLDS = {
        CorrelationType.STRONG_POSITIVE: 0.7,
        CorrelationType.STRONG_NEGATIVE: -0.7,
        CorrelationType.MODERATE_POSITIVE: 0.5,
        CorrelationType.MODERATE_NEGATIVE: -0.5,
        CorrelationType.WEAK_POSITIVE: 0.3,
        CorrelationType.WEAK_NEGATIVE: -0.3,
    }
    
    def __init__(self):
        """Initialize correlation engine"""
        self.metric_history: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
        self.max_history_points = 1000  # Keep 1000 most recent points
        
    def add_metric_value(self, metric_name: str, timestamp: datetime, value: float):
        """
        Add metric observation
        
        Args:
            metric_name: Unique metric identifier
            timestamp: Observation time
            value: Metric value
        """
        key = metric_name
        self.metric_history[key].append((timestamp, value))
        
        # Keep only recent data
        if len(self.metric_history[key]) > self.max_history_points:
            self.metric_history[key] = self.metric_history[key][-self.max_history_points:]
    
    def classify_correlation(self, correlation_coef: float) -> CorrelationType:
        """
        Classify correlation strength
        
        Args:
            correlation_coef: Pearson correlation coefficient (-1 to 1)
            
        Returns:
            CorrelationType classification
        """
        if correlation_coef > 0:
            if correlation_coef >= self.CORRELATION_THRESHOLDS[CorrelationType.STRONG_POSITIVE]:
                return CorrelationType.STRONG_POSITIVE
            elif correlation_coef >= self.CORRELATION_THRESHOLDS[CorrelationType.MODERATE_POSITIVE]:
                return CorrelationType.MODERATE_POSITIVE
            elif correlation_coef >= self.CORRELATION_THRESHOLDS[CorrelationType.WEAK_POSITIVE]:
                return CorrelationType.WEAK_POSITIVE
        elif correlation_coef < 0:
            if correlation_coef <= self.CORRELATION_THRESHOLDS[CorrelationType.STRONG_NEGATIVE]:
                return CorrelationType.STRONG_NEGATIVE
            elif correlation_coef <= self.CORRELATION_THRESHOLDS[CorrelationType.MODERATE_NEGATIVE]:
                return CorrelationType.MODERATE_NEGATIVE
            elif correlation_coef <= self.CORRELATION_THRESHOLDS[CorrelationType.WEAK_NEGATIVE]:
                return CorrelationType.WEAK_NEGATIVE
        
        return CorrelationType.NO_CORRELATION
    
    def compute_lagged_correlation(
        self,
        x_values: List[float],
        y_values: List[float],
        max_lag: int = 60
    ) -> Tuple[float, int, float]:
        """
        Compute correlation with time lag
        
        Args:
            x_values: First metric time series
            y_values: Second metric time series
            max_lag: Max lag to test in seconds (bins)
            
        Returns:
            (best_correlation, lag_offset, p_value)
        """
        if len(x_values) < 10:
            return 0.0, 0, 1.0
        
        x_array = np.array(x_values, dtype=np.float32)
        y_array = np.array(y_values, dtype=np.float32)
        
        # Normalize
        x_normalized = (x_array - np.mean(x_array)) / (np.std(x_array) + 1e-6)
        y_normalized = (y_array - np.mean(y_array)) / (np.std(y_array) + 1e-6)
        
        best_corr = 0.0
        best_lag = 0
        best_p_value = 1.0
        
        # Test different lags
        for lag in range(0, min(max_lag, len(x_array) // 2)):
            if lag == 0:
                # No lag
                x_test = x_normalized
                y_test = y_normalized
            else:
                # Lag y by lag steps
                x_test = x_normalized[:-lag]
                y_test = y_normalized[lag:]
            
            if len(x_test) < 3:
                continue
            
            # Compute Pearson correlation
            corr, p_value = stats.pearsonr(x_test, y_test)
            
            # Track best correlation
            if abs(corr) > abs(best_corr):
                best_corr = corr
                best_lag = lag
                best_p_value = p_value
        
        return best_corr, best_lag, best_p_value
    
    def analyze_metric_pair(
        self,
        metric_1: str,
        metric_2: str,
        endpoint: str,
        time_window_seconds: int = 300
    ) -> Optional[MetricCorrelation]:
        """
        Analyze correlation between two metrics
        
        Args:
            metric_1: First metric name
            metric_2: Second metric name
            endpoint: Endpoint context
            time_window_seconds: Analysis window (default 5 min)
            
        Returns:
            MetricCorrelation or None if insufficient data
        """
        # Get recent data for both metrics
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=time_window_seconds)
        
        # Extract values within time window
        values_1 = [
            v for t, v in self.metric_history[metric_1]
            if t >= cutoff
        ]
        values_2 = [
            v for t, v in self.metric_history[metric_2]
            if t >= cutoff
        ]
        
        # Need at least 10 samples
        if len(values_1) < 10 or len(values_2) < 10:
            return None
        
        # Ensure same length by truncating
        min_len = min(len(values_1), len(values_2))
        values_1 = values_1[-min_len:]
        values_2 = values_2[-min_len:]
        
        # Compute lagged correlation
        corr_coef, lag, p_value = self.compute_lagged_correlation(values_1, values_2)
        
        # Classify correlation
        corr_type = self.classify_correlation(corr_coef)
        
        # Skip if no correlation
        if corr_type == CorrelationType.NO_CORRELATION:
            return None
        
        result = MetricCorrelation(
            metric_1=metric_1,
            metric_2=metric_2,
            endpoint=endpoint,
            correlation_coefficient=corr_coef,
            correlation_type=corr_type,
            sample_count=min_len,
            p_value=p_value,
            lag_offset=lag,
            timestamp=now
        )
        
        return result
    
    def analyze_endpoint_correlations(
        self,
        endpoint: str,
        metrics: List[str],
        time_window_seconds: int = 300
    ) -> CorrelationSnapshot:
        """
        Analyze all correlations for an endpoint
        
        Args:
            endpoint: Endpoint to analyze
            metrics: List of metrics to correlate
            time_window_seconds: Analysis window
            
        Returns:
            CorrelationSnapshot with all correlations
        """
        correlations = []
        
        # Pairwise correlation analysis
        for i, metric_1 in enumerate(metrics):
            for metric_2 in metrics[i+1:]:
                corr = self.analyze_metric_pair(
                    metric_1, metric_2, endpoint,
                    time_window_seconds
                )
                
                if corr:
                    correlations.append(corr)
                    log.debug(
                        "Correlation found",
                        metric_1=metric_1,
                        metric_2=metric_2,
                        coefficient=corr.correlation_coefficient,
                        type=corr.correlation_type.value
                    )
        
        result = CorrelationSnapshot(
            timestamp=datetime.utcnow(),
            endpoint=endpoint,
            correlations=correlations,
            analysis_window_seconds=time_window_seconds
        )
        
        return result
    
    def find_correlated_metrics(
        self,
        anomalous_metric: str,
        endpoint: str,
        min_correlation: float = 0.5,
        time_window_seconds: int = 300
    ) -> List[MetricCorrelation]:
        """
        Find metrics correlated with anomalous metric
        
        Args:
            anomalous_metric: Metric showing anomaly
            endpoint: Endpoint context
            min_correlation: Minimum |correlation| to include
            time_window_seconds: Analysis window
            
        Returns:
            List of correlated metrics
        """
        correlated = []
        
        # Compare against all other metrics
        for other_metric in self.metric_history.keys():
            if other_metric == anomalous_metric:
                continue
            
            corr = self.analyze_metric_pair(
                anomalous_metric, other_metric, endpoint,
                time_window_seconds
            )
            
            if corr and abs(corr.correlation_coefficient) >= min_correlation:
                correlated.append(corr)
        
        # Sort by absolute correlation strength
        correlated.sort(
            key=lambda x: abs(x.correlation_coefficient),
            reverse=True
        )
        
        return correlated
    
    def detect_correlation_patterns(
        self,
        endpoint: str,
        time_window_seconds: int = 300
    ) -> Dict[str, List[str]]:
        """
        Detect groups of correlated metrics
        
        Args:
            endpoint: Endpoint to analyze
            time_window_seconds: Analysis window
            
        Returns:
            Dict mapping primary metrics to correlated metrics
        """
        patterns = {}
        
        # Get all metrics
        all_metrics = list(self.metric_history.keys())
        
        # Analyze correlations
        snapshot = self.analyze_endpoint_correlations(
            endpoint, all_metrics, time_window_seconds
        )
        
        # Group correlations
        for corr in snapshot.correlations:
            if abs(corr.correlation_coefficient) >= 0.5:
                # Add to both directions
                if corr.metric_1 not in patterns:
                    patterns[corr.metric_1] = []
                patterns[corr.metric_1].append(corr.metric_2)
                
                if corr.metric_2 not in patterns:
                    patterns[corr.metric_2] = []
                patterns[corr.metric_2].append(corr.metric_1)
        
        return patterns
    
    def clear_old_data(self, keep_seconds: int = 3600):
        """
        Clear old metric history
        
        Args:
            keep_seconds: Keep data from last N seconds
        """
        cutoff = datetime.utcnow() - timedelta(seconds=keep_seconds)
        
        for metric_name in self.metric_history:
            self.metric_history[metric_name] = [
                (t, v) for t, v in self.metric_history[metric_name]
                if t >= cutoff
            ]
        
        log.info("Cleared old correlation data", keep_seconds=keep_seconds)
