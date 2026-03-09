"""
Alert Manager Service

Consumes anomalies from Kafka and:
1. Groups related anomalies into incidents
2. Performs deduplication with sliding window
3. Applies cooldown periods per severity
4. Routes alerts to Slack, PagerDuty, email
5. Tracks alert states in PostgreSQL
"""

import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Set
from collections import defaultdict
from dataclasses import dataclass, asdict

import structlog
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
import redis

log = structlog.get_logger()


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class AnomalyData:
    """Anomaly from detection service"""
    timestamp: datetime
    endpoint: str
    metric_name: str
    is_anomaly: bool
    anomaly_score: float
    ensemble_confidence: float
    
    @classmethod
    def from_kafka_message(cls, msg: dict) -> 'AnomalyData':
        """Parse Kafka message"""
        return cls(
            timestamp=datetime.fromisoformat(msg['timestamp']),
            endpoint=msg['endpoint'],
            metric_name=msg['metric_name'],
            is_anomaly=msg['is_anomaly'],
            anomaly_score=msg['anomaly_score'],
            ensemble_confidence=msg['ensemble_confidence']
        )


@dataclass
class AlertState:
    """Alert state for deduplication and cooldown"""
    alert_id: str
    endpoint: str
    severity: str
    first_seen: datetime
    last_seen: datetime
    count: int = 1
    acknowledged: bool = False
    incident_id: Optional[str] = None


# ============================================================================
# Alert Manager
# ============================================================================

class AlertManager:
    """Manages alerts, deduplication, and routing"""
    
    SEVERITY_WEIGHTS = {
        'INFO': 1,
        'WARNING': 2,
        'CRITICAL': 3
    }
    
    SEVERITY_DETECTION_THRESHOLDS = {
        'INFO': (0.50, 0.60),      # anomaly_score, confidence
        'WARNING': (0.60, 0.75),
        'CRITICAL': (0.75, 0.85)
    }
    
    def __init__(self, config, redis_client: redis.Redis, dispatcher):
        """
        Initialize alert manager
        
        Args:
            config: Configuration
            redis_client: Redis for caching
            dispatcher: AlertDispatcher for routing
        """
        self.config = config
        self.redis = redis_client
        self.dispatcher = dispatcher
        
        # State tracking
        self.alert_cache: Dict[str, AlertState] = {}
        self.incident_cache: Dict[str, Set[str]] = defaultdict(set)  # incident_id -> alert_ids
        self.cooldowns: Dict[str, datetime] = {}  # endpoint_severity -> cooldown_time
        self.dedup_window = config.ALERT_DEDUP_WINDOW_SECONDS
        
    def determine_severity(self, anomaly: AnomalyData) -> Optional[str]:
        """
        Determine alert severity from anomaly
        
        Returns severity level or None if below INFO threshold
        """
        # Check against thresholds
        for severity in ['CRITICAL', 'WARNING', 'INFO']:
            min_score, min_conf = self.SEVERITY_DETECTION_THRESHOLDS[severity]
            if (anomaly.anomaly_score >= min_score and 
                anomaly.ensemble_confidence >= min_conf):
                return severity
        
        return None  # Below INFO threshold
    
    def _get_dedup_key(self, endpoint: str, severity: str) -> str:
        """Get deduplication key"""
        return f"{endpoint}_{severity}_dedup"
    
    def _get_cooldown_key(self, endpoint: str, severity: str) -> str:
        """Get cooldown cache key"""
        return f"{endpoint}_{severity}_cooldown"
    
    def is_in_cooldown(self, endpoint: str, severity: str) -> bool:
        """Check if alert is in cooldown period"""
        key = self._get_cooldown_key(endpoint, severity)
        
        # Check memory cache first
        if key in self.cooldowns:
            if datetime.utcnow() < self.cooldowns[key]:
                return True
            else:
                del self.cooldowns[key]
        
        # Check Redis
        if self.redis:
            try:
                if self.redis.exists(key):
                    return True
            except Exception as e:
                log.warning("Redis cooldown check failed", error=str(e))
        
        return False
    
    def set_cooldown(self, endpoint: str, severity: str):
        """Set cooldown period for severity"""
        if severity == 'CRITICAL':
            cooldown_sec = self.config.ALERT_COOLDOWN_CRITICAL
        elif severity == 'WARNING':
            cooldown_sec = self.config.ALERT_COOLDOWN_WARN
        else:
            cooldown_sec = self.config.ALERT_COOLDOWN_INFO
        
        key = self._get_cooldown_key(endpoint, severity)
        
        # Set in memory
        self.cooldowns[key] = datetime.utcnow() + timedelta(seconds=cooldown_sec)
        
        # Set in Redis
        if self.redis:
            try:
                self.redis.setex(key, cooldown_sec, '1')
            except Exception as e:
                log.warning("Redis cooldown set failed", error=str(e))
        
        log.info(
            "Cooldown activated",
            endpoint=endpoint,
            severity=severity,
            duration_sec=cooldown_sec
        )
    
    def is_duplicate(self, endpoint: str, severity: str) -> bool:
        """Check if alert is duplicate within dedup window"""
        key = self._get_dedup_key(endpoint, severity)
        
        if not self.redis:
            return False
        
        try:
            # Atomic increment with expiry
            if self.redis.incr(key) == 1:
                # First occurrence in window
                self.redis.expire(key, self.dedup_window)
                return False
            else:
                # Duplicate within window
                return True
        except Exception as e:
            log.warning("Redis dedup check failed", error=str(e))
            return False
    
    def create_alert(self, anomaly: AnomalyData, severity: str) -> Optional[Dict]:
        """
        Create alert from anomaly
        
        Returns alert dict or None if suppressed
        """
        # Check cooldown
        if self.is_in_cooldown(anomaly.endpoint, severity):
            log.debug(
                "Alert suppressed by cooldown",
                endpoint=anomaly.endpoint,
                severity=severity
            )
            return None
        
        # Check deduplication
        if self.is_duplicate(anomaly.endpoint, severity):
            log.debug(
                "Alert deduplicated",
                endpoint=anomaly.endpoint,
                severity=severity
            )
            return None
        
        # Create alert
        alert_id = str(uuid.uuid4())
        
        # Determine title and description
        title = f"{severity}: {anomaly.metric_name} anomaly on {anomaly.endpoint}"
        description = (
            f"Anomaly detected on {anomaly.endpoint}\n"
            f"Metric: {anomaly.metric_name}\n"
            f"Anomaly Score: {anomaly.anomaly_score:.2%}\n"
            f"Time: {anomaly.timestamp.isoformat()}"
        )
        
        # Build alert
        alert = {
            'alert_id': alert_id,
            'endpoint': anomaly.endpoint,
            'metric_name': anomaly.metric_name,
            'severity': severity,
            'title': title,
            'description': description,
            'timestamp': anomaly.timestamp.isoformat(),
            'anomaly_score': anomaly.anomaly_score,
            'ensemble_confidence': anomaly.ensemble_confidence,
            'acknowledged': False,
            'incident_id': None
        }
        
        # Cache alert state
        self.alert_cache[alert_id] = AlertState(
            alert_id=alert_id,
            endpoint=anomaly.endpoint,
            severity=severity,
            first_seen=anomaly.timestamp,
            last_seen=anomaly.timestamp
        )
        
        return alert
    
    def group_into_incident(self, alert: Dict) -> Optional[str]:
        """
        Group alert into existing incident or create new one
        
        Returns incident_id
        """
        endpoint = alert['endpoint']
        
        # Look for existing active incident on same endpoint
        for incident_id, alert_ids in self.incident_cache.items():
            # Check if incident is still active (within 15 minutes)
            first_alert = min(
                (self.alert_cache[aid] for aid in alert_ids),
                key=lambda a: a.first_seen
            )
            
            if (datetime.utcnow() - first_alert.last_seen).total_seconds() < 900:
                # Found active incident on same endpoint
                self.incident_cache[incident_id].add(alert['alert_id'])
                log.info(
                    "Alert grouped into incident",
                    alert_id=alert['alert_id'],
                    incident_id=incident_id
                )
                return incident_id
        
        # Create new incident
        incident_id = str(uuid.uuid4())
        self.incident_cache[incident_id].add(alert['alert_id'])
        
        log.info(
            "New incident created",
            incident_id=incident_id,
            alert_id=alert['alert_id']
        )
        
        return incident_id
    
    def get_severity_routing(self) -> Dict[str, List[str]]:
        """Get severity-> channels routing"""
        return {
            'CRITICAL': ['slack', 'pagerduty'],
            'WARNING': ['slack'],
            'INFO': ['slack']
        }
    
    def process_anomaly(self, anomaly: AnomalyData) -> Optional[Dict]:
        """
        Process anomaly and return alert if one should be sent
        
        Returns alert dict or None
        """
        # Only process confirmed anomalies
        if not anomaly.is_anomaly:
            return None
        
        # Determine severity
        severity = self.determine_severity(anomaly)
        if severity is None:
            return None
        
        # Create alert (may be suppressed)
        alert = self.create_alert(anomaly, severity)
        if alert is None:
            return None
        
        # Group into incident
        incident_id = self.group_into_incident(alert)
        alert['incident_id'] = incident_id
        
        # Update cache
        if alert['alert_id'] in self.alert_cache:
            self.alert_cache[alert['alert_id']].incident_id = incident_id
        
        # Set cooldown for this endpoint/severity
        self.set_cooldown(anomaly.endpoint, severity)
        
        return alert


# ============================================================================
# Streaming Service
# ============================================================================

class AlertingService:
    """Kafka-based alerting service"""
    
    def __init__(self, config, dispatcher):
        self.config = config
        self.dispatcher = dispatcher
        self.consumer = None
        self.producer = None
        self.redis_client = None
        self.manager = None
        self.running = False
        
    def setup(self) -> bool:
        """Initialize Kafka connections and Redis"""
        try:
            # Setup Redis
            try:
                self.redis_client = redis.Redis(
                    host=self.config.REDIS_HOST,
                    port=self.config.REDIS_PORT,
                    db=self.config.REDIS_DB,
                    password=self.config.REDIS_PASSWORD,
                    socket_connect_timeout=5
                )
                self.redis_client.ping()
                log.info("Redis connected")
            except Exception as e:
                log.warning("Redis not available, using memory-only dedup", error=str(e))
                self.redis_client = None
            
            # Setup Kafka consumer
            bootstrap_servers = self.config.KAFKA_BOOTSTRAP_SERVERS.split(',')
            self.consumer = KafkaConsumer(
                self.config.KAFKA_TOPICS['anomalies'],
                bootstrap_servers=bootstrap_servers,
                group_id='alert_manager',
                auto_offset_reset='latest',
                consumer_timeout_ms=1000,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            
            # Setup Kafka producer
            self.producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            
            # Initialize alert manager
            self.manager = AlertManager(
                config=self.config,
                redis_client=self.redis_client,
                dispatcher=self.dispatcher
            )
            
            log.info("Service setup complete")
            return True
        except Exception as e:
            log.error("Setup failed", error=str(e))
            return False
    
    def run(self):
        """Main service loop"""
        if not self.setup():
            log.error("Setup failed, exiting")
            return
        
        self.running = True
        log.info("Starting alerting service")
        
        try:
            while self.running:
                try:
                    for message in self.consumer:
                        if not self.running:
                            break
                        
                        try:
                            # Parse anomaly
                            anomaly = AnomalyData.from_kafka_message(message.value)
                            
                            # Process anomaly
                            alert = self.manager.process_anomaly(anomaly)
                            
                            if alert:
                                # Route alert to channels
                                severity_routing = self.manager.get_severity_routing()
                                results = self.dispatcher.send_to_all(
                                    alert,
                                    severity_routing=severity_routing
                                )
                                
                                # Publish alert to Kafka
                                self.producer.send(
                                    self.config.KAFKA_TOPICS['alerts'],
                                    value=alert
                                )
                                
                                log.info(
                                    "Alert created and routed",
                                    alert_id=alert['alert_id'],
                                    severity=alert['severity'],
                                    endpoint=alert['endpoint'],
                                    routing_results=results
                                )
                        
                        except Exception as e:
                            log.error("Message processing failed", error=str(e))
                            continue
                
                except KafkaError as e:
                    log.error("Kafka error", error=str(e))
                    continue
        
        except KeyboardInterrupt:
            log.info("Shutdown requested")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        self.running = False
        if self.consumer:
            self.consumer.close()
        if self.producer:
            self.producer.close()
        if self.redis_client:
            self.redis_client.close()
        log.info("Service stopped")
