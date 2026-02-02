"""
Metrics Storage Layer

Provides a clean interface for storing and retrieving aggregated metrics.
Supports multiple storage backends (in-memory, SQLite) with a unified API.

This layer enables:
- Persistent storage of aggregated metrics from the aggregator
- Efficient querying for historical data by the detector
- Clean separation of storage concerns from business logic
- Easy switching between storage backends

Architecture:
- Abstract base class defines the interface
- Concrete implementations handle specific storage mechanisms
- Factory pattern for backend selection
"""

import os
import sqlite3
import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd


class MetricsStorageBackend(ABC):
    """Abstract base class for metrics storage backends."""

    @abstractmethod
    def store_metrics(self, metrics: List[Dict[str, Any]]) -> bool:
        """Store a batch of aggregated metrics."""
        pass

    @abstractmethod
    def get_metrics(self,
                   endpoint: Optional[str] = None,
                   window_minutes: Optional[int] = None,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None,
                   limit: Optional[int] = None) -> pd.DataFrame:
        """Query metrics with optional filters."""
        pass

    @abstractmethod
    def get_latest_metrics(self,
                          endpoint: Optional[str] = None,
                          window_minutes: Optional[int] = None) -> pd.DataFrame:
        """Get the most recent metrics for each endpoint/window combination."""
        pass

    @abstractmethod
    def clear_old_data(self, days_to_keep: int = 30) -> int:
        """Remove data older than specified days. Returns number of records removed."""
        pass


class InMemoryMetricsStorage(MetricsStorageBackend):
    """In-memory storage backend for testing and development."""

    def __init__(self):
        self._metrics: List[Dict[str, Any]] = []
        self._max_records = 10000  # Prevent unbounded memory usage

    def store_metrics(self, metrics: List[Dict[str, Any]]) -> bool:
        """Store metrics in memory."""
        try:
            for metric in metrics:
                # Ensure timestamp is datetime object
                if isinstance(metric.get('timestamp'), str):
                    metric = metric.copy()
                    metric['window_end'] = pd.to_datetime(metric['timestamp'])

                self._metrics.append(metric)

            # Maintain max records limit (remove oldest)
            if len(self._metrics) > self._max_records:
                excess = len(self._metrics) - self._max_records
                self._metrics = self._metrics[excess:]

            return True
        except Exception as e:
            print(f"Error storing metrics in memory: {e}")
            return False

    def get_metrics(self,
                   endpoint: Optional[str] = None,
                   window_minutes: Optional[int] = None,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None,
                   limit: Optional[int] = None) -> pd.DataFrame:
        """Query metrics from memory."""
        try:
            df = pd.DataFrame(self._metrics)

            if df.empty:
                return pd.DataFrame()

            # Apply filters
            if endpoint:
                df = df[df['endpoint'] == endpoint]
            if window_minutes:
                df = df[df['window_minutes'] == window_minutes]
            if start_time:
                df = df[df['window_end'] >= start_time]
            if end_time:
                df = df[df['window_end'] <= end_time]

            # Sort by timestamp descending
            df = df.sort_values('window_end', ascending=False)

            if limit:
                df = df.head(limit)

            return df
        except Exception as e:
            print(f"Error querying metrics from memory: {e}")
            return pd.DataFrame()

    def get_latest_metrics(self,
                          endpoint: Optional[str] = None,
                          window_minutes: Optional[int] = None) -> pd.DataFrame:
        """Get latest metrics from memory."""
        try:
            df = pd.DataFrame(self._metrics)

            if df.empty:
                return pd.DataFrame()

            # Group by endpoint and window, get most recent
            df = df.sort_values('window_end', ascending=False)
            df = df.drop_duplicates(subset=['endpoint', 'window_minutes'], keep='first')

            # Apply filters
            if endpoint:
                df = df[df['endpoint'] == endpoint]
            if window_minutes:
                df = df[df['window_minutes'] == window_minutes]

            return df
        except Exception as e:
            print(f"Error getting latest metrics from memory: {e}")
            return pd.DataFrame()

    def clear_old_data(self, days_to_keep: int = 30) -> int:
        """Clear old data from memory."""
        try:
            cutoff = datetime.now() - timedelta(days=days_to_keep)
            old_count = len(self._metrics)

            self._metrics = [
                m for m in self._metrics
                if pd.to_datetime(m.get('window_end', m.get('timestamp'))) > cutoff
            ]

            return old_count - len(self._metrics)
        except Exception as e:
            print(f"Error clearing old data from memory: {e}")
            return 0


class SQLiteMetricsStorage(MetricsStorageBackend):
    """SQLite-based persistent storage backend for production use."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # Go up three levels: storage/ -> src/ -> project_root/ -> data/
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            data_dir = os.path.join(base_dir, 'data')
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, 'metrics_store.db')

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    endpoint TEXT NOT NULL,
                    window_minutes INTEGER NOT NULL,
                    window_end TEXT NOT NULL,
                    avg_latency REAL NOT NULL,
                    p95_latency REAL NOT NULL,
                    error_rate REAL NOT NULL,
                    request_volume INTEGER NOT NULL,
                    response_size_variance REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(endpoint, window_minutes, window_end)
                )
            ''')

            # Create indexes for performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_endpoint_window ON metrics(endpoint, window_minutes)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_window_end ON metrics(window_end)')
            conn.commit()

    def store_metrics(self, metrics: List[Dict[str, Any]]) -> bool:
        """Store metrics in SQLite database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                for metric in metrics:
                    # Normalize data format
                    window_minutes = metric.get('window_minutes')
                    if not window_minutes and 'window' in metric:
                        # Convert "5m" format to minutes
                        window_str = metric['window'].rstrip('m')
                        window_minutes = int(window_str)

                    conn.execute('''
                        INSERT OR REPLACE INTO metrics
                        (endpoint, window_minutes, window_end, avg_latency, p95_latency,
                         error_rate, request_volume, response_size_variance)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        metric['endpoint'],
                        window_minutes,
                        metric.get('window_end', metric.get('timestamp')),
                        metric['avg_latency'],
                        metric['p95_latency'],
                        metric['error_rate'],
                        metric['request_volume'],
                        metric.get('response_size_variance', metric.get('response_var', 0))
                    ))
                conn.commit()
            return True
        except Exception as e:
            print(f"Error storing metrics in SQLite: {e}")
            return False

    def get_metrics(self,
                   endpoint: Optional[str] = None,
                   window_minutes: Optional[int] = None,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None,
                   limit: Optional[int] = None) -> pd.DataFrame:
        """Query metrics from SQLite database."""
        try:
            query = "SELECT * FROM metrics WHERE 1=1"
            params = []

            if endpoint:
                query += " AND endpoint = ?"
                params.append(endpoint)

            if window_minutes:
                query += " AND window_minutes = ?"
                params.append(window_minutes)

            if start_time:
                query += " AND window_end >= ?"
                params.append(start_time.isoformat())

            if end_time:
                query += " AND window_end <= ?"
                params.append(end_time.isoformat())

            query += " ORDER BY window_end DESC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=params)

            if not df.empty:
                # Convert window_end to datetime with mixed format support
                df['window_end'] = pd.to_datetime(df['window_end'], format='mixed', utc=True)
                df['created_at'] = pd.to_datetime(df['created_at'], format='mixed', utc=True)

            return df
        except Exception as e:
            print(f"Error querying metrics from SQLite: {e}")
            return pd.DataFrame()

    def get_latest_metrics(self,
                          endpoint: Optional[str] = None,
                          window_minutes: Optional[int] = None) -> pd.DataFrame:
        """Get latest metrics from SQLite database."""
        try:
            # Use a subquery to get the most recent record for each endpoint/window combination
            query = """
                SELECT m.* FROM metrics m
                INNER JOIN (
                    SELECT endpoint, window_minutes, MAX(window_end) as max_window_end
                    FROM metrics
                    GROUP BY endpoint, window_minutes
                ) latest ON m.endpoint = latest.endpoint
                        AND m.window_minutes = latest.window_minutes
                        AND m.window_end = latest.max_window_end
            """

            conditions = []
            params = []

            if endpoint:
                conditions.append("m.endpoint = ?")
                params.append(endpoint)

            if window_minutes:
                conditions.append("m.window_minutes = ?")
                params.append(window_minutes)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, conn, params=params)

            if not df.empty:
                # Convert timestamps
                df['window_end'] = pd.to_datetime(df['window_end'], format='mixed', utc=True)
                df['created_at'] = pd.to_datetime(df['created_at'], format='mixed', utc=True)

            return df
        except Exception as e:
            print(f"Error getting latest metrics from SQLite: {e}")
            return pd.DataFrame()

    def clear_old_data(self, days_to_keep: int = 30) -> int:
        """Remove data older than specified days from SQLite."""
        try:
            cutoff = (datetime.now() - timedelta(days=days_to_keep)).isoformat()

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM metrics WHERE window_end < ?", (cutoff,))
                old_count = cursor.fetchone()[0]

                cursor.execute("DELETE FROM metrics WHERE window_end < ?", (cutoff,))
                deleted_count = cursor.rowcount

                conn.commit()

                # Vacuum to reclaim space
                conn.execute("VACUUM")

            return deleted_count
        except Exception as e:
            print(f"Error clearing old data from SQLite: {e}")
            return 0


class MetricsStore:
    """
    Main interface for metrics storage.

    Provides a unified API that can use different storage backends.
    Defaults to SQLite for persistence, but can be configured for in-memory storage.
    """

    def __init__(self, backend: str = 'sqlite', **kwargs):
        """
        Initialize the metrics store.

        Args:
            backend: 'sqlite' or 'memory'
            **kwargs: Additional arguments passed to backend constructor
        """
        if backend == 'sqlite':
            self._backend = SQLiteMetricsStorage(**kwargs)
        elif backend == 'memory':
            self._backend = InMemoryMetricsStorage(**kwargs)
        else:
            raise ValueError(f"Unsupported backend: {backend}")

    def store_metrics(self, metrics: List[Dict[str, Any]]) -> bool:
        """Store aggregated metrics."""
        return self._backend.store_metrics(metrics)

    def get_metrics(self,
                   endpoint: Optional[str] = None,
                   window_minutes: Optional[int] = None,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None,
                   limit: Optional[int] = None) -> pd.DataFrame:
        """Query historical metrics with filters."""
        return self._backend.get_metrics(endpoint, window_minutes, start_time, end_time, limit)

    def get_latest_metrics(self,
                          endpoint: Optional[str] = None,
                          window_minutes: Optional[int] = None) -> pd.DataFrame:
        """Get most recent metrics for analysis."""
        return self._backend.get_latest_metrics(endpoint, window_minutes)

    def clear_old_data(self, days_to_keep: int = 30) -> int:
        """Clean up old data to manage storage."""
        return self._backend.clear_old_data(days_to_keep)

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        # This would be backend-specific, simplified for now
        return {
            'backend_type': type(self._backend).__name__,
            'db_path': getattr(self._backend, 'db_path', None)
        }


# Global instance for easy access
_default_store = None

def get_metrics_store(backend: str = 'sqlite', **kwargs) -> MetricsStore:
    """Factory function to get or create the default metrics store."""
    global _default_store
    if _default_store is None or kwargs.get('force_new', False):
        _default_store = MetricsStore(backend, **kwargs)
    return _default_store


if __name__ == '__main__':
    # Test the storage layer
    print("Testing Metrics Storage Layer...")

    # Test with in-memory backend
    print("\n1. Testing in-memory storage:")
    memory_store = MetricsStore('memory')

    test_metrics = [
        {
            'endpoint': '/api/users',
            'window_minutes': 5,
            'window_end': '2026-01-05T10:00:00Z',
            'avg_latency': 85.0,
            'p95_latency': 120.0,
            'error_rate': 0.02,
            'request_volume': 100,
            'response_size_variance': 1000.0
        },
        {
            'endpoint': '/checkout',
            'window_minutes': 5,
            'window_end': '2026-01-05T10:00:00Z',
            'avg_latency': 200.0,
            'p95_latency': 450.0,
            'error_rate': 0.05,
            'request_volume': 50,
            'response_size_variance': 5000.0
        }
    ]

    success = memory_store.store_metrics(test_metrics)
    print(f"Storage successful: {success}")

    latest = memory_store.get_latest_metrics()
    print(f"Retrieved {len(latest)} latest metrics")

    # Test with SQLite backend
    print("\n2. Testing SQLite storage:")
    sqlite_store = MetricsStore('sqlite')

    success = sqlite_store.store_metrics(test_metrics)
    print(f"Storage successful: {success}")

    latest_sqlite = sqlite_store.get_latest_metrics()
    print(f"Retrieved {len(latest_sqlite)} latest metrics from SQLite")

    print("\n3. Testing query filters:")
    checkout_metrics = sqlite_store.get_metrics(endpoint='/checkout')
    print(f"Found {len(checkout_metrics)} metrics for /checkout endpoint")

    print("\n✅ Metrics Storage Layer tests completed!")