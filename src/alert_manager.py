"""Intelligent Alert Manager

Handles alert deduplication, cool-down periods, severity classification,
and multi-channel routing to prevent alert fatigue and ensure operational efficiency.

Features:
- Deduplication: Prevents duplicate alerts for same endpoint/severity within time window
- Cool-down: Prevents alert spam with configurable cool-down periods
- Routing: Routes alerts to appropriate channels based on severity
- Channels: Console, Slack, Email support
"""

from typing import Dict, Any, List, Optional, Set
import time
import json
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from datetime import datetime, timezone, timedelta
import threading

logger = logging.getLogger(__name__)

# Import config with fallbacks
try:
    from .config import (
        ALERT_SEVERITY_LEVELS, ALERT_COOLDOWN_INFO, ALERT_COOLDOWN_WARN, ALERT_COOLDOWN_CRITICAL,
        ALERT_DEDUP_WINDOW, SLACK_WEBHOOK_URL, EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT,
        EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM, EMAIL_TO,
        ALERT_CHANNELS_INFO, ALERT_CHANNELS_WARN, ALERT_CHANNELS_CRITICAL
    )
    from .storage.alert_store import get_alert_store
except ImportError:
    # Fallback for testing
    ALERT_SEVERITY_LEVELS = ['INFO', 'WARN', 'CRITICAL']
    ALERT_COOLDOWN_INFO = 3600
    ALERT_COOLDOWN_WARN = 1800
    ALERT_COOLDOWN_CRITICAL = 300
    ALERT_DEDUP_WINDOW = 600
    SLACK_WEBHOOK_URL = None
    EMAIL_SMTP_SERVER = None
    EMAIL_SMTP_PORT = 587
    EMAIL_USERNAME = None
    EMAIL_PASSWORD = None
    EMAIL_FROM = 'alerts@api-monitor.local'
    EMAIL_TO = []
    ALERT_CHANNELS_INFO = ['console']
    ALERT_CHANNELS_WARN = ['console', 'slack']
    ALERT_CHANNELS_CRITICAL = ['console', 'slack', 'email']

    def get_alert_store():
        # Mock store for testing
        class MockStore:
            def store_alert(self, alert): return str(uuid.uuid4())
        return MockStore()


class AlertManager:
    """Intelligent alert manager with deduplication and routing."""

    def __init__(self):
        self._lock = threading.RLock()
        self._recent_alerts: Dict[str, float] = {}  # endpoint_severity -> last_alert_time
        self._cooldowns = {
            'INFO': ALERT_COOLDOWN_INFO,
            'WARN': ALERT_COOLDOWN_WARN,
            'CRITICAL': ALERT_COOLDOWN_CRITICAL
        }
        self._channels = {
            'INFO': ALERT_CHANNELS_INFO,
            'WARN': ALERT_CHANNELS_WARN,
            'CRITICAL': ALERT_CHANNELS_CRITICAL
        }

    def classify_severity(self, alert: Dict[str, Any]) -> str:
        """Classify alert severity based on signal characteristics."""
        signals = alert.get('signals', [])
        if not signals:
            return 'INFO'

        # Check for critical conditions
        has_critical_signal = any(s.get('severity') == 'HIGH' for s in signals)
        has_multiple_signals = len(signals) >= 3
        has_error_spike = any(
            s.get('metric_name') == 'error_rate' and
            s.get('current_value', 0) > 0.05  # 5% error rate
            for s in signals
        )
        has_latency_spike = any(
            s.get('metric_name') in ['avg_latency', 'p95_latency'] and
            s.get('deviation_ratio', 0) > 2.0
            for s in signals
        )

        if has_critical_signal or has_multiple_signals or (has_error_spike and has_latency_spike):
            return 'CRITICAL'
        elif has_error_spike or has_latency_spike or len(signals) >= 2:
            return 'WARN'
        else:
            return 'INFO'

    def _should_deduplicate(self, alert: Dict[str, Any]) -> bool:
        """Check if alert should be deduplicated based on recent alerts."""
        endpoint = alert.get('endpoint', 'unknown')
        severity = alert.get('severity', 'INFO')
        key = f"{endpoint}_{severity}"

        now = time.time()
        last_alert_time = self._recent_alerts.get(key, 0)

        if now - last_alert_time < ALERT_DEDUP_WINDOW:
            logger.debug(f"Deduplicating alert for {key} - too recent")
            return True

        return False

    def _is_in_cooldown(self, alert: Dict[str, Any]) -> bool:
        """Check if alert is in cool-down period."""
        endpoint = alert.get('endpoint', 'unknown')
        severity = alert.get('severity', 'INFO')
        key = f"{endpoint}_{severity}"

        now = time.time()
        last_alert_time = self._recent_alerts.get(key, 0)
        cooldown = self._cooldowns.get(severity, ALERT_COOLDOWN_INFO)

        if now - last_alert_time < cooldown:
            logger.debug(f"Alert for {key} in cool-down ({cooldown}s remaining)")
            return True

        return False

    def _update_alert_tracking(self, alert: Dict[str, Any]):
        """Update tracking for deduplication and cool-down."""
        endpoint = alert.get('endpoint', 'unknown')
        severity = alert.get('severity', 'INFO')
        key = f"{endpoint}_{severity}"

        with self._lock:
            self._recent_alerts[key] = time.time()

    def _send_console(self, alert: Dict[str, Any]) -> bool:
        """Send alert to console."""
        try:
            ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            severity = alert.get('severity', 'INFO')
            endpoint = alert.get('endpoint', 'unknown')
            explanation = alert.get('explanation', 'No explanation')

            print(f"\n{'='*60}")
            print(f"🚨 ALERT [{severity}] - {endpoint}")
            print(f"Time: {ts}")
            print(f"Explanation: {explanation}")

            if 'insights' in alert and alert['insights']:
                print("Insights:")
                for insight in alert['insights']:
                    print(f"  • {insight}")

            if 'recommendations' in alert and alert['recommendations']:
                print("Recommendations:")
                for rec in alert['recommendations']:
                    print(f"  • {rec}")

            print(f"{'='*60}\n")
            return True
        except Exception as e:
            logger.error(f"Failed to send console alert: {e}")
            return False

    def _send_slack(self, alert: Dict[str, Any]) -> bool:
        """Send alert to Slack."""
        if not SLACK_WEBHOOK_URL:
            return False

        try:
            import httpx

            severity = alert.get('severity', 'INFO')
            endpoint = alert.get('endpoint', 'unknown')
            explanation = alert.get('explanation', 'No explanation')

            # Create rich Slack message
            emoji_map = {'CRITICAL': '🔴', 'WARN': '🟡', 'INFO': 'ℹ️'}
            emoji = emoji_map.get(severity, '⚠️')

            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {severity} Alert: {endpoint}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": explanation
                    }
                }
            ]

            # Add insights and recommendations if available
            if alert.get('insights'):
                insights_text = "\n".join(f"• {i}" for i in alert['insights'][:3])  # Limit to 3
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Insights:*\n{insights_text}"
                    }
                })

            if alert.get('recommendations'):
                recs_text = "\n".join(f"• {r}" for r in alert['recommendations'][:3])  # Limit to 3
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Recommendations:*\n{recs_text}"
                    }
                })

            payload = {"blocks": blocks}

            response = httpx.post(SLACK_WEBHOOK_URL, json=payload, timeout=10.0)
            return response.status_code == 200

        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False

    def _send_email(self, alert: Dict[str, Any]) -> bool:
        """Send alert via email."""
        if not all([EMAIL_SMTP_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_TO]):
            return False

        try:
            severity = alert.get('severity', 'INFO')
            endpoint = alert.get('endpoint', 'unknown')
            explanation = alert.get('explanation', 'No explanation')

            msg = MIMEMultipart()
            msg['From'] = EMAIL_FROM
            msg['To'] = ', '.join(EMAIL_TO)
            msg['Subject'] = f"[{severity}] API Alert: {endpoint}"

            body = f"""
API Degradation Alert

Severity: {severity}
Endpoint: {endpoint}
Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

Explanation:
{explanation}

"""

            if alert.get('insights'):
                body += "\nInsights:\n" + "\n".join(f"• {i}" for i in alert['insights'])

            if alert.get('recommendations'):
                body += "\n\nRecommendations:\n" + "\n".join(f"• {r}" for r in alert['recommendations'])

            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
            server.starttls()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            text = msg.as_string()
            server.sendmail(EMAIL_FROM, EMAIL_TO, text)
            server.quit()

            return True

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False

    def _route_alert(self, alert: Dict[str, Any]) -> bool:
        """Route alert to configured channels based on severity."""
        severity = alert.get('severity', 'INFO')
        channels = self._channels.get(severity, ['console'])

        # At least one channel must succeed
        success = False
        for channel in channels:
            if channel == 'console':
                if self._send_console(alert):
                    success = True
            elif channel == 'slack':
                self._send_slack(alert)  # Don't fail if Slack fails
            elif channel == 'email':
                self._send_email(alert)  # Don't fail if email fails

        return success

    def process_alert(self, alert: Dict[str, Any]) -> bool:
        """Process an alert through the intelligent alerting pipeline.

        Returns True if alert was sent, False if deduplicated/cooled-down.
        """
        # Ensure severity is set
        if 'severity' not in alert:
            alert['severity'] = self.classify_severity(alert)

        # Check deduplication
        if self._should_deduplicate(alert):
            logger.info(f"Alert deduplicated: {alert.get('endpoint')} {alert.get('severity')}")
            return False

        # Check cool-down
        if self._is_in_cooldown(alert):
            logger.info(f"Alert in cool-down: {alert.get('endpoint')} {alert.get('severity')}")
            return False

        # Store alert
        try:
            store = get_alert_store()
            alert_id = store.store_alert(alert)
            alert['id'] = alert_id
        except Exception as e:
            logger.error(f"Failed to store alert: {e}")

        # Route to channels
        success = self._route_alert(alert)

        # Update tracking
        self._update_alert_tracking(alert)

        logger.info(f"Alert processed: {alert.get('endpoint')} {alert.get('severity')} - sent: {success}")
        return success

    def get_recent_alerts(self, endpoint: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent alerts, optionally filtered by endpoint and/or severity."""
        # This would need to be implemented to query the alert store
        # For now, return empty list
        return []

    def clear_cooldowns(self):
        """Clear all cool-down tracking (useful for testing)."""
        with self._lock:
            self._recent_alerts.clear()


# Global instance
_alert_manager = AlertManager()

def get_alert_manager() -> AlertManager:
    """Get the global alert manager instance."""
    return _alert_manager

def process_alert(alert: Dict[str, Any]) -> bool:
    """Process an alert through the intelligent alerting pipeline."""
    return _alert_manager.process_alert(alert)