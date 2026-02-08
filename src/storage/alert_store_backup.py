"""Alert store backed by SQLite.

This module provides a single `AlertStore` class with clear, testable
methods for storing and retrieving alerts. It is intentionally small and
uses only the standard library for persistence.
"""
from typing import Dict, Any, List, Optional
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path


class AlertStore:
    """SQLite backed alert store.

    The store accepts a filesystem path to an sqlite database. Each method
    opens a short-lived connection to avoid sharing connections across
    threads/processes.
    """

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

    def store_alert(self, alert: Dict[str, Any]) -> str:
        """Store alert and return generated id.

        The alert dict must contain: endpoint, severity, window, anomalous_metrics,
        explanation. Optional: anomaly_count, avg_deviation, max_deviation, insights,
        recommendations, timestamp.
        """
        import uuid

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
