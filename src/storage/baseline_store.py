"""
Baseline Storage Layer

Provides persistent storage and retrieval of baseline statistics for anomaly detection.
Supports multiple storage backends with a unified API.

This layer enables:
- Persistent storage of computed baseline statistics
- Efficient retrieval for real-time anomaly detection
- Rolling updates of baseline models
- Easy switching between storage backends

Architecture:
- Abstract base class defines the interface
- Concrete implementations handle specific storage mechanisms
- Supports both simple rolling statistics and advanced models (EWMA, seasonal)
"""

import os
import sqlite3
import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd


class BaselineStorageBackend(ABC):
    """Abstract base class for baseline storage backends."""

    @abstractmethod
    def store_baseline(self, endpoint: str, metric_name: str, baseline_data: Dict[str, Any]) -> bool:
        """Store baseline statistics for an endpoint/metric combination."""
        pass

    @abstractmethod
    def get_baseline(self, endpoint: str, metric_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve baseline statistics for an endpoint/metric combination."""
        pass

    @abstractmethod
    def get_all_baselines(self, endpoint: Optional[str] = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get all baselines, optionally filtered by endpoint."""
        pass

    @abstractmethod
    def update_baseline(self, endpoint: str, metric_name: str, new_value: float, timestamp: datetime) -> bool:
        """Update baseline with new observation using rolling statistics."""
        pass

    @abstractmethod
    def clear_old_data(self, days_to_keep: int = 90) -> int:
        """Remove baseline data older than specified days. Returns number of records removed."""
        pass


class InMemoryBaselineStorage(BaselineStorageBackend):
    """In-memory storage backend for baseline statistics."""

    def __init__(self):
        # endpoint -> metric_name -> baseline_data
        self._baselines: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._max_records = 10000  # Prevent unbounded memory usage

    def store_baseline(self, endpoint: str, metric_name: str, baseline_data: Dict[str, Any]) -> bool:
        """Store baseline statistics in memory."""
        try:
            if endpoint not in self._baselines:
                self._baselines[endpoint] = {}

            baseline_data['last_updated'] = datetime.now()
            self._baselines[endpoint][metric_name] = baseline_data
            return True
        except Exception as e:
            print(f"Error storing baseline in memory: {e}")
            return False

    def get_baseline(self, endpoint: str, metric_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve baseline from memory."""
        try:
            return self._baselines.get(endpoint, {}).get(metric_name)
        except Exception:
            return None

    def get_all_baselines(self, endpoint: Optional[str] = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get all baselines from memory."""
        try:
            if endpoint:
                return {endpoint: self._baselines.get(endpoint, {})}
            return self._baselines.copy()
        except Exception:
            return {}

    def update_baseline(self, endpoint: str, metric_name: str, new_value: float, timestamp: datetime) -> bool:
        """Update baseline with new observation using rolling statistics."""
        try:
            if endpoint not in self._baselines:
                self._baselines[endpoint] = {}

            if metric_name not in self._baselines[endpoint]:
                # Initialize baseline with first observation
                self._baselines[endpoint][metric_name] = {
                    'mean': new_value,
                    'std': 0.0,
                    'count': 1,
                    'last_updated': timestamp,
                    'ewma': new_value,  # Initialize EWMA
                    'ewma_variance': 0.0
                }
                return True

            baseline = self._baselines[endpoint][metric_name]

            # Update rolling statistics
            old_count = baseline['count']
            old_mean = baseline['mean']
            old_std = baseline['std']

            new_count = old_count + 1
            new_mean = old_mean + (new_value - old_mean) / new_count

            # Update variance using Welford's online algorithm
            if old_count > 1:
                old_variance = old_std ** 2
                new_variance = old_variance + (new_value - old_mean) * (new_value - new_mean) / new_count
                new_std = new_variance ** 0.5 if new_variance > 0 else 0.0
            else:
                new_std = abs(new_value - old_mean)

            # Update EWMA (alpha = 0.1 for responsiveness)
            alpha = 0.1
            old_ewma = baseline.get('ewma', old_mean)
            new_ewma = alpha * new_value + (1 - alpha) * old_ewma

            # Update EWMA variance estimate
            old_ewma_var = baseline.get('ewma_variance', old_std ** 2)
            ewma_error = new_value - old_ewma
            new_ewma_var = (1 - alpha) * (old_ewma_var + alpha * ewma_error ** 2)

            baseline.update({
                'mean': new_mean,
                'std': new_std,
                'count': new_count,
                'last_updated': timestamp,
                'ewma': new_ewma,
                'ewma_variance': new_ewma_var
            })

            return True
        except Exception as e:
            print(f"Error updating baseline: {e}")
            return False

    def clear_old_data(self, days_to_keep: int = 90) -> int:
        """Clear old baseline data (not applicable for in-memory)."""
        return 0


class SQLiteBaselineStorage(BaselineStorageBackend):
    """SQLite storage backend for baseline statistics."""

    def __init__(self, db_path: str = "baselines.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS baselines (
                    endpoint TEXT,
                    metric_name TEXT,
                    baseline_data TEXT,
                    last_updated TIMESTAMP,
                    PRIMARY KEY (endpoint, metric_name)
                )
            ''')
            conn.commit()

    def store_baseline(self, endpoint: str, metric_name: str, baseline_data: Dict[str, Any]) -> bool:
        """Store baseline in SQLite."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                baseline_data['last_updated'] = datetime.now().isoformat()
                conn.execute('''
                    INSERT OR REPLACE INTO baselines (endpoint, metric_name, baseline_data, last_updated)
                    VALUES (?, ?, ?, ?)
                ''', (endpoint, metric_name, json.dumps(baseline_data), datetime.now()))
                conn.commit()
            return True
        except Exception as e:
            print(f"Error storing baseline in SQLite: {e}")
            return False

    def get_baseline(self, endpoint: str, metric_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve baseline from SQLite."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT baseline_data FROM baselines
                    WHERE endpoint = ? AND metric_name = ?
                ''', (endpoint, metric_name))
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
        except Exception as e:
            print(f"Error retrieving baseline from SQLite: {e}")
        return None

    def get_all_baselines(self, endpoint: Optional[str] = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get all baselines from SQLite."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if endpoint:
                    cursor = conn.execute('''
                        SELECT endpoint, metric_name, baseline_data FROM baselines
                        WHERE endpoint = ?
                    ''', (endpoint,))
                else:
                    cursor = conn.execute('''
                        SELECT endpoint, metric_name, baseline_data FROM baselines
                    ''')

                baselines = {}
                for row in cursor:
                    ep, metric, data = row
                    if ep not in baselines:
                        baselines[ep] = {}
                    baselines[ep][metric] = json.loads(data)
                return baselines
        except Exception as e:
            print(f"Error retrieving all baselines from SQLite: {e}")
            return {}

    def update_baseline(self, endpoint: str, metric_name: str, new_value: float, timestamp: datetime) -> bool:
        """Update baseline with new observation."""
        try:
            current = self.get_baseline(endpoint, metric_name)
            if current is None:
                # Initialize
                baseline_data = {
                    'mean': new_value,
                    'std': 0.0,
                    'count': 1,
                    'ewma': new_value,
                    'ewma_variance': 0.0
                }
            else:
                # Update using same logic as in-memory version
                old_count = current['count']
                old_mean = current['mean']
                old_std = current['std']

                new_count = old_count + 1
                new_mean = old_mean + (new_value - old_mean) / new_count

                if old_count > 1:
                    old_variance = old_std ** 2
                    new_variance = old_variance + (new_value - old_mean) * (new_value - new_mean) / new_count
                    new_std = new_variance ** 0.5 if new_variance > 0 else 0.0
                else:
                    new_std = abs(new_value - old_mean)

                # EWMA update
                alpha = 0.1
                old_ewma = current.get('ewma', old_mean)
                new_ewma = alpha * new_value + (1 - alpha) * old_ewma

                old_ewma_var = current.get('ewma_variance', old_std ** 2)
                ewma_error = new_value - old_ewma
                new_ewma_var = (1 - alpha) * (old_ewma_var + alpha * ewma_error ** 2)

                baseline_data = {
                    'mean': new_mean,
                    'std': new_std,
                    'count': new_count,
                    'ewma': new_ewma,
                    'ewma_variance': new_ewma_var
                }

            return self.store_baseline(endpoint, metric_name, baseline_data)
        except Exception as e:
            print(f"Error updating baseline in SQLite: {e}")
            return False

    def clear_old_data(self, days_to_keep: int = 90) -> int:
        """Remove old baseline data."""
        try:
            cutoff = datetime.now() - timedelta(days=days_to_keep)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    DELETE FROM baselines WHERE last_updated < ?
                ''', (cutoff,))
                deleted_count = cursor.rowcount
                conn.commit()
                return deleted_count
        except Exception as e:
            print(f"Error clearing old baseline data: {e}")
            return 0


# Factory function for baseline storage
def create_baseline_storage(backend: str = "memory", **kwargs) -> BaselineStorageBackend:
    """Factory function to create baseline storage backend."""
    if backend == "memory":
        return InMemoryBaselineStorage()
    elif backend == "sqlite":
        db_path = kwargs.get('db_path', 'baselines.db')
        return SQLiteBaselineStorage(db_path)
    else:
        raise ValueError(f"Unknown baseline storage backend: {backend}")


# Default global instance
_baseline_store: Optional[BaselineStorageBackend] = None


def get_baseline_store(backend: str = "memory", **kwargs) -> BaselineStorageBackend:
    """Get the global baseline storage instance."""
    global _baseline_store
    if _baseline_store is None or kwargs.get('force_new', False):
        _baseline_store = create_baseline_storage(backend, **kwargs)
    return _baseline_store