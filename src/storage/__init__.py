"""
Storage Layer Package

Provides persistent storage interfaces for the API Degradation Detection System.
"""

from .metrics_store import MetricsStore, get_metrics_store

__all__ = ['MetricsStore', 'get_metrics_store']