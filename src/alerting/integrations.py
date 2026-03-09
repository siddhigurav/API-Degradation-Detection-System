"""
Alert Channel Integrations

Supports multiple notification channels:
- Slack
- PagerDuty
- Email
"""

import json
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from datetime import datetime
from dataclasses import dataclass

import structlog
import httpx

log = structlog.get_logger()


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class AlertMessage:
    """Alert message to send"""
    alert_id: str
    endpoint: str
    severity: str  # INFO, WARNING, CRITICAL
    title: str
    description: str
    timestamp: datetime
    metrics: Dict[str, float]
    anomaly_score: float
    incident_id: Optional[str] = None
    run_book_url: Optional[str] = None


# ============================================================================
# Abstract Base Class
# ============================================================================

class AlertChannel(ABC):
    """Abstract alert notification channel"""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.name = self.__class__.__name__
        
    @abstractmethod
    def send(self, alert: AlertMessage) -> bool:
        """
        Send alert to channel
        
        Args:
            alert: AlertMessage to send
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """Test channel connectivity"""
        pass


# ============================================================================
# Slack Integration
# ============================================================================

class SlackChannel(AlertChannel):
    """Slack webhook-based notification"""
    
    SEVERITY_COLORS = {
        'INFO': '#36a64f',      # Green
        'WARNING': '#ff9900',   # Orange
        'CRITICAL': '#ff0000'   # Red
    }
    
    SEVERITY_EMOJI = {
        'INFO': 'ℹ️',
        'WARNING': '⚠️',
        'CRITICAL': '🚨'
    }
    
    def __init__(self, webhook_url: str, channel: str = '#alerts', enabled: bool = True):
        """
        Initialize Slack integration
        
        Args:
            webhook_url: Slack incoming webhook URL
            channel: Slack channel (optional, overrides webhook default)
            enabled: Whether to send alerts
        """
        super().__init__(enabled)
        self.webhook_url = webhook_url
        self.channel = channel
        self.http_client = httpx.AsyncClient(timeout=10.0)
        
    def _format_message(self, alert: AlertMessage) -> dict:
        """Format alert as Slack message"""
        emoji = self.SEVERITY_EMOJI.get(alert.severity, '•')
        color = self.SEVERITY_COLORS.get(alert.severity, '#999999')
        
        # Format metrics
        metrics_text = '\n'.join(
            f"• {k}: {v:.2f}" for k, v in alert.metrics.items()
        )
        
        return {
            "channel": self.channel,
            "username": "API Monitor Bot",
            "icon_emoji": ":chart_with_upwards_trend:",
            "attachments": [
                {
                    "fallback": f"{emoji} {alert.severity}: {alert.title}",
                    "color": color,
                    "title": f"{emoji} {alert.title}",
                    "title_link": alert.run_book_url or "https://api-monitor.local",
                    "text": alert.description,
                    "fields": [
                        {
                            "title": "Endpoint",
                            "value": f"`{alert.endpoint}`",
                            "short": True
                        },
                        {
                            "title": "Severity",
                            "value": alert.severity,
                            "short": True
                        },
                        {
                            "title": "Anomaly Score",
                            "value": f"{alert.anomaly_score:.2%}",
                            "short": True
                        },
                        {
                            "title": "Alert ID",
                            "value": alert.alert_id,
                            "short": True
                        },
                        {
                            "title": "Metrics",
                            "value": metrics_text,
                            "short": False
                        }
                    ],
                    "footer": "API Degradation Detection System",
                    "ts": int(alert.timestamp.timestamp())
                }
            ]
        }
    
    def send(self, alert: AlertMessage) -> bool:
        """Send alert to Slack"""
        if not self.enabled or not self.webhook_url:
            return False
        
        try:
            message = self._format_message(alert)
            
            # Use async to avoid blocking
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._send_async(message))
            loop.close()
            
            return result
        except Exception as e:
            log.error("Slack send failed", error=str(e), alert_id=alert.alert_id)
            return False
    
    async def _send_async(self, message: dict) -> bool:
        """Send async"""
        try:
            response = await self.http_client.post(self.webhook_url, json=message)
            
            if response.status_code == 200:
                log.info("Slack notification sent", webhook_url=self.webhook_url[:20])
                return True
            else:
                log.error("Slack API error", status=response.status_code, text=response.text)
                return False
        except Exception as e:
            log.error("Slack HTTP error", error=str(e))
            return False
    
    def test_connection(self) -> bool:
        """Test Slack webhook"""
        if not self.webhook_url:
            log.warning("Slack webhook not configured")
            return False
        
        try:
            test_message = {
                "text": "✅ API Monitor Slack integration test successful!"
            }
            
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.http_client.post(
                self.webhook_url,
                json=test_message,
                timeout=5.0
            ))
            loop.close()
            
            if result.status_code == 200:
                log.info("Slack connection test passed")
                return True
            else:
                log.error("Slack test failed", status=result.status_code)
                return False
        except Exception as e:
            log.error("Slack connection test failed", error=str(e))
            return False


# ============================================================================
# PagerDuty Integration
# ============================================================================

class PagerDutyChannel(AlertChannel):
    """PagerDuty event-based notification"""
    
    EVENT_API_URL = "https://events.pagerduty.com/v2/enqueue"
    
    SEVERITY_MAP = {
        'INFO': 'info',
        'WARNING': 'warning',
        'CRITICAL': 'critical'
    }
    
    def __init__(self, api_key: str, service_id: str, enabled: bool = True):
        """
        Initialize PagerDuty integration
        
        Args:
            api_key: PagerDuty integration key (Events API v2)
            service_id: PagerDuty service ID
            enabled: Whether to send alerts
        """
        super().__init__(enabled)
        self.api_key = api_key
        self.service_id = service_id
        self.http_client = httpx.AsyncClient(timeout=10.0)
        
    def _format_event(self, alert: AlertMessage) -> dict:
        """Format alert as PagerDuty event"""
        return {
            "routing_key": self.api_key,
            "event_action": "trigger",
            "dedup_key": alert.alert_id,
            "payload": {
                "summary": f"{alert.severity}: {alert.title}",
                "severity": self.SEVERITY_MAP.get(alert.severity, 'error'),
                "source": alert.endpoint,
                "timestamp": alert.timestamp.isoformat(),
                "custom_details": {
                    "endpoint": alert.endpoint,
                    "description": alert.description,
                    "anomaly_score": alert.anomaly_score,
                    "metrics": alert.metrics,
                    "incident_id": alert.incident_id,
                    "alert_id": alert.alert_id,
                    "run_book_url": alert.run_book_url
                }
            }
        }
    
    def send(self, alert: AlertMessage) -> bool:
        """Send alert to PagerDuty"""
        if not self.enabled or not self.api_key:
            return False
        
        try:
            event = self._format_event(alert)
            
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._send_async(event))
            loop.close()
            
            return result
        except Exception as e:
            log.error("PagerDuty send failed", error=str(e), alert_id=alert.alert_id)
            return False
    
    async def _send_async(self, event: dict) -> bool:
        """Send async"""
        try:
            response = await self.http_client.post(
                self.EVENT_API_URL,
                json=event,
                headers={"Accept": "application/vnd.pagerduty+json;version=2"}
            )
            
            if response.status_code == 202:
                log.info("PagerDuty event sent", dedup_key=event['dedup_key'])
                return True
            else:
                log.error("PagerDuty API error", status=response.status_code, text=response.text)
                return False
        except Exception as e:
            log.error("PagerDuty HTTP error", error=str(e))
            return False
    
    def test_connection(self) -> bool:
        """Test PagerDuty connectivity"""
        if not self.api_key:
            log.warning("PagerDuty API key not configured")
            return False
        
        try:
            test_event = {
                "routing_key": self.api_key,
                "event_action": "trigger",
                "dedup_key": "pagerduty_test",
                "payload": {
                    "summary": "✅ API Monitor PagerDuty integration test successful!",
                    "severity": "info",
                    "source": "api-monitor-test"
                }
            }
            
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.http_client.post(
                self.EVENT_API_URL,
                json=test_event,
                timeout=5.0
            ))
            loop.close()
            
            if result.status_code == 202:
                log.info("PagerDuty connection test passed")
                return True
            else:
                log.error("PagerDuty test failed", status=result.status_code)
                return False
        except Exception as e:
            log.error("PagerDuty connection test failed", error=str(e))
            return False


# ============================================================================
# Email Integration
# ============================================================================

class EmailChannel(AlertChannel):
    """Email-based notification (SMTP)"""
    
    def __init__(self, smtp_server: str, smtp_port: int, username: str, password: str,
                 from_address: str, to_addresses: List[str], enabled: bool = True):
        """
        Initialize Email integration
        
        Args:
            smtp_server: SMTP server hostname
            smtp_port: SMTP port (usually 587 or 465)
            username: SMTP username
            password: SMTP password
            from_address: Email 'From' address
            to_addresses: List of recipient addresses
            enabled: Whether to send emails
        """
        super().__init__(enabled)
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_address = from_address
        self.to_addresses = to_addresses
        
    def _format_email(self, alert: AlertMessage) -> Tuple[str, str, str]:
        """Format alert as email"""
        subject = f"[{alert.severity}] {alert.title}"
        
        metrics_html = '\n'.join(
            f"<li><strong>{k}:</strong> {v:.2f}</li>"
            for k, v in alert.metrics.items()
        )
        
        body = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #333;">{alert.title}</h2>
                <p><strong>Severity:</strong> {alert.severity}</p>
                <p><strong>Endpoint:</strong> <code>{alert.endpoint}</code></p>
                <p><strong>Anomaly Score:</strong> {alert.anomaly_score:.2%}</p>
                <p><strong>Time:</strong> {alert.timestamp.isoformat()}</p>
                
                <h3>Description</h3>
                <p>{alert.description}</p>
                
                <h3>Metrics</h3>
                <ul>
                    {metrics_html}
                </ul>
                
                <p><small>Alert ID: {alert.alert_id}</small></p>
            </body>
        </html>
        """
        
        return subject, body, self.from_address
    
    def send(self, alert: AlertMessage) -> bool:
        """Send alert via email"""
        if not self.enabled or not self.smtp_server or not self.to_addresses:
            return False
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            subject, body, from_addr = self._format_email(alert)
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = from_addr
            msg['To'] = ', '.join(self.to_addresses)
            
            # Attach HTML content
            msg.attach(MIMEText(body, 'html'))
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(from_addr, self.to_addresses, msg.as_string())
            
            log.info("Email sent", to=self.to_addresses, alert_id=alert.alert_id)
            return True
        except Exception as e:
            log.error("Email send failed", error=str(e), alert_id=alert.alert_id)
            return False
    
    def test_connection(self) -> bool:
        """Test SMTP connection"""
        if not self.smtp_server:
            log.warning("Email SMTP server not configured")
            return False
        
        try:
            import smtplib
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=5) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.noop()
            
            log.info("Email connection test passed")
            return True
        except Exception as e:
            log.error("Email connection test failed", error=str(e))
            return False


# ============================================================================
# Multi-Channel Dispatcher
# ============================================================================

class AlertDispatcher:
    """Dispatches alerts to multiple channels"""
    
    def __init__(self):
        self.channels: Dict[str, AlertChannel] = {}
        
    def register_channel(self, channel: AlertChannel):
        """Register alert channel"""
        self.channels[channel.name] = channel
        log.info("Alert channel registered", channel=channel.name)
        
    def send_to_all(self, alert: AlertMessage, severity_routing: Optional[Dict[str, List[str]]] = None) -> Dict[str, bool]:
        """
        Send alert to appropriate channels based on severity
        
        Args:
            alert: Alert to send
            severity_routing: Map of severity to channel names
                e.g., {'CRITICAL': ['slack', 'pagerduty'], 'WARNING': ['slack']}
                If None, sends to all channels
        
        Returns:
            Dict mapping channel name to send result
        """
        results = {}
        
        if severity_routing and alert.severity in severity_routing:
            channel_names = severity_routing[alert.severity]
        else:
            channel_names = list(self.channels.keys())
        
        for channel_name in channel_names:
            if channel_name not in self.channels:
                log.warning("Channel not found", channel=channel_name)
                results[channel_name] = False
                continue
            
            channel = self.channels[channel_name]
            if not channel.enabled:
                log.debug("Channel disabled", channel=channel_name)
                results[channel_name] = False
                continue
            
            try:
                success = channel.send(alert)
                results[channel_name] = success
            except Exception as e:
                log.error("Channel send failed", channel=channel_name, error=str(e))
                results[channel_name] = False
        
        return results
    
    def test_all_connections(self) -> Dict[str, bool]:
        """Test all channel connections"""
        results = {}
        
        for name, channel in self.channels.items():
            try:
                success = channel.test_connection()
                results[name] = success
                if success:
                    log.info("Channel test passed", channel=name)
                else:
                    log.warning("Channel test failed", channel=name)
            except Exception as e:
                log.error("Channel test error", channel=name, error=str(e))
                results[name] = False
        
        return results
