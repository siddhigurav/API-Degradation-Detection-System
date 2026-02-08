"""
Alert Storage Layer

Provides persistent storage and retrieval of alerts with multiple backend support.
Supports in-memory, SQLite, and future Redis/time-series backends.

This layer enables:
- Persistent storage of alerts with full context
- Efficient querying and status updates
- Easy switching between storage backends
- Scalability from development to production

Architecture:
- Abstract base class defines the interface
- Concrete implementations handle specific storage mechanisms
- Factory pattern for backend selection
"""

import os
import sqlite3
import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional


class AlertStorageBackend(ABC):
    """Abstract base class for alert storage backends."""

    @abstractmethod
    def store_alert(self, alert: Dict[str, Any]) -> str:
        """Store alert and return generated id."""
        pass

    @abstractmethod
    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve alert by id."""
        pass

    @abstractmethod
    def get_all_alerts(self, limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all alerts with optional status filter."""
        pass

    @abstractmethod
    def update_alert_status(self, alert_id: str, status: str) -> bool:
        """Update alert status."""
        pass

    @abstractmethod
    def clear_old_data(self, days_to_keep: int = 90) -> int:
        """Remove alerts older than specified days. Returns number of records removed."""
        pass


class InMemoryAlertStorage(AlertStorageBackend):
    """In-memory storage backend for alerts (development/testing)."""

    def __init__(self):
        self._alerts: Dict[str, Dict[str, Any]] = {}
        self._max_records = 1000  # Prevent unbounded memory usage

    def store_alert(self, alert: Dict[str, Any]) -> str:
        """Store alert in memory and return generated id."""
        alert_id = str(uuid.uuid4())
        alert_copy = alert.copy()
        alert_copy['id'] = alert_id
        alert_copy['created_at'] = datetime.now(timezone.utc).isoformat()
        alert_copy['status'] = alert_copy.get('status', 'active')

        self._alerts[alert_id] = alert_copy

        # Maintain max records limit (remove oldest)
        if len(self._alerts) > self._max_records:
            # Remove oldest alerts (by created_at)
            sorted_alerts = sorted(self._alerts.items(),
                                 key=lambda x: x[1]['created_at'])
            excess = len(self._alerts) - self._max_records
            for i in range(excess):
                del self._alerts[sorted_alerts[i][0]]

        return alert_id

    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve alert from memory."""
        return self._alerts.get(alert_id)

    def get_all_alerts(self, limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all alerts from memory with optional status filter."""
        alerts = list(self._alerts.values())

        if status:
            alerts = [a for a in alerts if a.get('status') == status]

        # Sort by created_at descending (newest first)
        alerts.sort(key=lambda x: x['created_at'], reverse=True)

        return alerts[:limit]

    def update_alert_status(self, alert_id: str, status: str) -> bool:
        """Update alert status in memory."""
        if alert_id in self._alerts:
            self._alerts[alert_id]['status'] = status
            return True
        return False

    def clear_old_data(self, days_to_keep: int = 90) -> int:
        """Remove old alerts from memory. Returns number removed."""
        cutoff = (datetime.now(timezone.utc).timestamp() -
                 days_to_keep * 24 * 60 * 60)

        to_remove = []
        for alert_id, alert in self._alerts.items():
            try:
                created_ts = datetime.fromisoformat(alert['created_at'].replace('Z', '+00:00')).timestamp()
                if created_ts < cutoff:
                    to_remove.append(alert_id)
            except:
                continue

        for alert_id in to_remove:
            del self._alerts[alert_id]

        return len(to_remove)

    def clear(self) -> None:
        """Clear all stored alerts."""
        self._alerts = []


class SQLiteAlertStorage(AlertStorageBackend):
    """SQLite backed alert store for production use."""

    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path))
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    endpoint TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    window TEXT NOT NULL,
                    anomaly_count INTEGER NOT NULL,
                    avg_deviation REAL NOT NULL,
                    max_deviation REAL NOT NULL,
                    anomalous_metrics TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    insights TEXT NOT NULL,
                    recommendations TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active'
                )
                """
            )
            conn.commit()

    def store_alert(self, alert: Dict[str, Any]) -> str:
        """Store alert and return generated id."""
        alert_id = str(uuid.uuid4())
        timestamp = alert.get('timestamp') or datetime.now(timezone.utc).isoformat()

        anomalous_metrics = json.dumps(alert.get('anomalous_metrics', []))
        insights = json.dumps(alert.get('insights', []))
        recommendations = json.dumps(alert.get('recommendations', []))

        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO alerts
                (id, endpoint, severity, window, anomaly_count, avg_deviation, max_deviation,
                 anomalous_metrics, explanation, insights, recommendations, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    alert['endpoint'],
                    alert['severity'],
                    alert['window'],
                    int(alert.get('anomaly_count', 0)),
                    float(alert.get('avg_deviation', 0.0)),
                    float(alert.get('max_deviation', 0.0)),
                    anomalous_metrics,
                    alert['explanation'],
                    insights,
                    recommendations,
                    timestamp,
                ),
            )

        return alert_id

    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute('SELECT * FROM alerts WHERE id = ?', (alert_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def get_all_alerts(self, limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = 'SELECT * FROM alerts'
        params = []
        if status:
            query += ' WHERE status = ?'
            params.append(status)
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)

        with self._get_conn() as conn:
            cur = conn.execute(query, params)
            rows = cur.fetchall()
            return [self._row_to_dict(r) for r in rows]

    def update_alert_status(self, alert_id: str, status: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute('UPDATE alerts SET status = ? WHERE id = ?', (status, alert_id))
            return cur.rowcount > 0

    def clear_old_data(self, days_to_keep: int = 90) -> int:
        """Remove alerts older than specified days from SQLite."""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).isoformat()

            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM alerts WHERE created_at < ?", (cutoff,))
                old_count = cursor.fetchone()[0]

                cursor.execute("DELETE FROM alerts WHERE created_at < ?", (cutoff,))
                deleted_count = cursor.rowcount

                conn.commit()

            return deleted_count
        except Exception:
            return 0

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            'id': row['id'],
            'endpoint': row['endpoint'],
            'severity': row['severity'],
            'window': row['window'],
            'anomaly_count': row['anomaly_count'],
            'avg_deviation': row['avg_deviation'],
            'max_deviation': row['max_deviation'],
            'anomalous_metrics': json.loads(row['anomalous_metrics']),
            'explanation': row['explanation'],
            'insights': json.loads(row['insights']),
            'recommendations': json.loads(row['recommendations']),
            'timestamp': row['timestamp'],
            'created_at': row['created_at'],
            'status': row['status'],
        }

class RedisAlertStorage(AlertStorageBackend):
    """Redis-backed alert store for high-performance caching and state management.

    Uses Redis for fast access and optional persistence. Suitable for:
    - High-throughput environments
    - Distributed deployments
    - Fast state sharing across services
    """

    def __init__(self, redis_url: str = 'redis://localhost:6379/0', key_prefix: str = 'alerts:'):
        try:
            import redis
            self.redis = redis.from_url(redis_url)
            self.key_prefix = key_prefix
            self.alerts_key = f"{key_prefix}list"
            self.id_counter_key = f"{key_prefix}id_counter"
        except ImportError:
            raise ImportError("Redis backend requires 'redis' package. Install with: pip install redis")

    def store_alert(self, alert: Dict[str, Any]) -> str:
        """Store alert in Redis with auto-incrementing ID."""
        alert_id = str(self.redis.incr(self.id_counter_key))
        alert_copy = alert.copy()
        alert_copy['id'] = alert_id
        alert_copy['created_at'] = datetime.now(timezone.utc).isoformat()

        # Store alert data
        alert_key = f"{self.key_prefix}alert:{alert_id}"
        self.redis.set(alert_key, json.dumps(alert_copy))

        # Add to alerts list for enumeration
        self.redis.lpush(self.alerts_key, alert_id)

        # Set expiration (90 days)
        self.redis.expire(alert_key, 90 * 24 * 60 * 60)

        return alert_id

    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve alert from Redis."""
        alert_key = f"{self.key_prefix}alert:{alert_id}"
        data = self.redis.get(alert_key)
        if data:
            return json.loads(data)
        return None

    def get_all_alerts(self, limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all alerts from Redis with optional status filter."""
        # Get recent alert IDs
        alert_ids = self.redis.lrange(self.alerts_key, 0, limit - 1)

        alerts = []
        for alert_id_bytes in alert_ids:
            alert_id = alert_id_bytes.decode('utf-8')
            alert = self.get_alert(alert_id)
            if alert and (status is None or alert.get('status') == status):
                alerts.append(alert)

        return alerts

    def update_alert_status(self, alert_id: str, status: str) -> bool:
        """Update alert status in Redis."""
        alert = self.get_alert(alert_id)
        if alert:
            alert['status'] = status
            alert_key = f"{self.key_prefix}alert:{alert_id}"
            self.redis.set(alert_key, json.dumps(alert))
            return True
        return False

class TimescaleAlertStorage(AlertStorageBackend):
    """TimescaleDB-backed alert store for time-series analytics and historical analysis.

    Uses TimescaleDB (PostgreSQL extension) for:
    - Efficient time-series queries
    - Historical data retention
    - Advanced analytics and backtesting
    - Scalable storage for high-volume deployments
    """

    def __init__(self, connection_string: str = 'postgresql://localhost:5432/alerts'):
        try:
            import psycopg2
            import psycopg2.extras
            self.conn_string = connection_string
            self._init_db()
        except ImportError:
            raise ImportError("TimescaleDB backend requires 'psycopg2' package. Install with: pip install psycopg2-binary")

    def _get_conn(self):
        import psycopg2
        import psycopg2.extras
        return psycopg2.connect(self.conn_string)

    def _init_db(self):
        """Initialize TimescaleDB schema."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                # Create hypertable for alerts
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS alerts (
                        id TEXT PRIMARY KEY,
                        endpoint TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        window TEXT NOT NULL,
                        anomaly_count INTEGER NOT NULL,
                        avg_deviation REAL NOT NULL,
                        max_deviation REAL NOT NULL,
                        anomalous_metrics JSONB NOT NULL,
                        explanation TEXT NOT NULL,
                        insights JSONB NOT NULL,
                        recommendations JSONB NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        status TEXT DEFAULT 'active'
                    )
                ''')

                # Convert to hypertable if not already
                cur.execute('''
                    SELECT create_hypertable('alerts', 'created_at', if_not_exists => TRUE)
                ''')

                # Create indexes for performance
                cur.execute('CREATE INDEX IF NOT EXISTS idx_alerts_endpoint ON alerts(endpoint)')
                cur.execute('CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity)')
                cur.execute('CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)')
                cur.execute('CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC)')

            conn.commit()

    def store_alert(self, alert: Dict[str, Any]) -> str:
        """Store alert in TimescaleDB."""
        import uuid
        alert_id = str(uuid.uuid4())

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO alerts
                    (id, endpoint, severity, window, anomaly_count, avg_deviation, max_deviation,
                     anomalous_metrics, explanation, insights, recommendations, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    alert_id,
                    alert['endpoint'],
                    alert['severity'],
                    alert['window'],
                    int(alert.get('anomaly_count', 0)),
                    float(alert.get('avg_deviation', 0.0)),
                    float(alert.get('max_deviation', 0.0)),
                    json.dumps(alert.get('anomalous_metrics', [])),
                    alert['explanation'],
                    json.dumps(alert.get('insights', [])),
                    json.dumps(alert.get('recommendations', [])),
                    alert.get('timestamp') or datetime.now(timezone.utc).isoformat(),
                ))
            conn.commit()

        return alert_id

    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve alert from TimescaleDB."""
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute('SELECT * FROM alerts WHERE id = %s', (alert_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def get_all_alerts(self, limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all alerts from TimescaleDB with optional status filter."""
        query = 'SELECT * FROM alerts'
        params = []

        if status:
            query += ' WHERE status = %s'
            params.append(status)

        query += ' ORDER BY created_at DESC LIMIT %s'
        params.append(limit)

        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]

    def update_alert_status(self, alert_id: str, status: str) -> bool:
        """Update alert status in TimescaleDB."""
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE alerts SET status = %s WHERE id = %s', (status, alert_id))
                return cur.rowcount > 0

    def clear_old_data(self, days_to_keep: int = 90) -> int:
        """Remove alerts older than specified days from TimescaleDB."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).isoformat()

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM alerts WHERE created_at < %s", (cutoff,))
                old_count = cur.fetchone()[0]

                cur.execute("DELETE FROM alerts WHERE created_at < %s", (cutoff,))
                deleted_count = cur.rowcount

            conn.commit()

        return deleted_count


class AlertStore:
    """
    Main interface for alert storage.

    Provides a unified API that can use different storage backends.
    Defaults to in-memory for development, SQLite for production.
    """

    def __init__(self, backend: str = 'memory', **kwargs):
        """
        Initialize the alert store.

        Args:
            backend: 'memory', 'sqlite', or 'redis'
            **kwargs: Additional arguments passed to backend constructor
        """
        if backend == 'sqlite':
            db_path = kwargs.get('db_path', 'data/alerts.db')
            self._backend = SQLiteAlertStorage(db_path)
        elif backend == 'memory':
            self._backend = InMemoryAlertStorage()
        elif backend == 'redis':
            redis_url = kwargs.get('redis_url', 'redis://localhost:6379/0')
            key_prefix = kwargs.get('key_prefix', 'alerts:')
            self._backend = RedisAlertStorage(redis_url, key_prefix)
        elif backend == 'timescale':
            connection_string = kwargs.get('connection_string', 'postgresql://localhost:5432/alerts')
            self._backend = TimescaleAlertStorage(connection_string)
        else:
            raise ValueError(f"Unsupported backend: {backend}. Supported: memory, sqlite, redis, timescale")

    def store_alert(self, alert: Dict[str, Any]) -> str:
        """Store alert and return generated id."""
        return self._backend.store_alert(alert)

    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve alert by id."""
        return self._backend.get_alert(alert_id)

    def get_all_alerts(self, limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all alerts with optional status filter."""
        return self._backend.get_all_alerts(limit, status)

    def update_alert_status(self, alert_id: str, status: str) -> bool:
        """Update alert status."""
        return self._backend.update_alert_status(alert_id, status)

    def clear_old_data(self, days_to_keep: int = 90) -> int:
        """Clean up old alerts."""
        return self._backend.clear_old_data(days_to_keep)


# Global instance for easy access
_default_store = None

def get_alert_store(backend: str = 'memory', **kwargs) -> AlertStore:
    """Factory function to get or create the default alert store."""
    global _default_store
    if _default_store is None or kwargs.get('force_new', False):
        _default_store = AlertStore(backend, **kwargs)
    return _default_store


# Backward compatibility - keep the old AlertStore class as an alias
AlertStoreLegacy = SQLiteAlertStorage


if __name__ == '__main__':
    # Test the new multi-backend storage layer
    print("Testing Multi-Backend Alert Storage Layer")
    print("=" * 50)

    # Test in-memory backend
    print("\n1. Testing in-memory backend:")
    memory_store = AlertStore('memory')
    test_alert = {
        'endpoint': '/api/test',
        'severity': 'WARN',
        'window': '5m',
        'anomaly_count': 1,
        'avg_deviation': 2.5,
        'max_deviation': 3.0,
        'anomalous_metrics': ['avg_latency'],
        'explanation': 'Test alert',
        'insights': ['Test insight'],
        'recommendations': ['Test recommendation']
    }

    alert_id = memory_store.store_alert(test_alert)
    print(f"Stored alert with ID: {alert_id}")

    retrieved = memory_store.get_alert(alert_id)
    print(f"Retrieved alert: {retrieved is not None}")

    # Test SQLite backend
    print("\n2. Testing SQLite backend:")
    sqlite_store = AlertStore('sqlite', db_path='data/test_alerts.db')
    alert_id_sqlite = sqlite_store.store_alert(test_alert)
    print(f"Stored alert with ID: {alert_id_sqlite}")

    retrieved_sqlite = sqlite_store.get_alert(alert_id_sqlite)
    print(f"Retrieved alert: {retrieved_sqlite is not None}")

    # Test factory function
    print("\n3. Testing factory function:")
    default_store = get_alert_store('memory')
    factory_id = default_store.store_alert(test_alert)
    print(f"Factory-created store works: {factory_id is not None}")

    print("\n4. Available backends:")
    print("   - memory: In-memory storage (development/testing)")
    print("   - sqlite: SQLite database (production default)")
    print("   - redis: Redis cache (high-performance, requires 'redis' package)")
    print("   - timescale: TimescaleDB (time-series analytics, requires 'psycopg2')")
    print("\n   Usage examples:")
    print("   AlertStore('memory')                    # In-memory")
    print("   AlertStore('sqlite', db_path='data/alerts.db')  # SQLite")
    print("   AlertStore('redis', redis_url='redis://localhost:6379/0')  # Redis")
    print("   AlertStore('timescale', connection_string='postgresql://...')  # TimescaleDB")
