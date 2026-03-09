"""
Root Cause Analysis Service

Kafka consumer service for RCA analysis.
- Consumes anomalies from Kafka
- Performs correlation, causal, and dependency analysis
- Generates RCA results and stores in PostgreSQL
- Publishes root-causes to Kafka topic
"""

import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import structlog
from collections import defaultdict
import asyncio

from kafka import KafkaConsumer, KafkaProducer
import psycopg2
from psycopg2.extras import RealDictCursor

from src.rca.models import (
    RCAResult, RCAMetricContribution, CausalityConfidence,
    RCAFinding, HistoricalIncidentMatch
)
from src.rca.correlation_engine import CorrelationEngine
from src.rca.causal_analyzer import CausalAnalyzer
from src.rca.dependency_analyzer import DependencyAnalyzer
from src.config import KAFKA_BROKERS, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

log = structlog.get_logger()


class RCAService:
    """Root Cause Analysis service"""
    
    def __init__(self):
        """Initialize RCA service"""
        self.correlation_engine = CorrelationEngine()
        self.causal_analyzer = CausalAnalyzer()
        self.dependency_analyzer = DependencyAnalyzer()
        self.db_connection = None
        self.kafka_producer = None
        self.kafka_consumer = None
        self.incident_history: Dict[str, List[Dict]] = defaultdict(list)
        
    async def start(self):
        """Start the RCA service"""
        log.info("Starting RCA Service")
        
        # Initialize Kafka
        await self._init_kafka()
        
        # Initialize database
        self._init_database()
        
        # Load incident history
        self._load_incident_history()
        
        # Start consuming anomalies
        await self._consume_anomalies()
    
    async def _init_kafka(self):
        """Initialize Kafka producer and consumer"""
        try:
            # Producer for root-causes topic
            self.kafka_producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                retries=3
            )
            log.info("Kafka producer initialized")
            
            # Consumer for anomalies topic
            self.kafka_consumer = KafkaConsumer(
                'anomalies',
                bootstrap_servers=KAFKA_BROKERS,
                group_id='rca-service',
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',
                enable_auto_commit=True
            )
            log.info("Kafka consumer initialized")
            
        except Exception as e:
            log.error("Kafka initialization failed", error=str(e))
            raise
    
    def _init_database(self):
        """Initialize database connection"""
        try:
            self.db_connection = psycopg2.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME
            )
            log.info("Database connection established")
            self._create_tables()
        except Exception as e:
            log.error("Database initialization failed", error=str(e))
            raise
    
    def _create_tables(self):
        """Create RCA tables if not exist"""
        if not self.db_connection:
            return
        
        cursor = self.db_connection.cursor()
        
        try:
            # RCA results table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS rca_analyses (
                id SERIAL PRIMARY KEY,
                incident_id VARCHAR(255) UNIQUE NOT NULL,
                endpoint VARCHAR(255) NOT NULL,
                anomalous_metric VARCHAR(255) NOT NULL,
                root_causes TEXT NOT NULL,
                contributing_factors TEXT NOT NULL,
                symptoms TEXT NOT NULL,
                evidence TEXT NOT NULL,
                recommendations TEXT NOT NULL,
                confidence FLOAT NOT NULL,
                ttd_seconds INT,
                analysis_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            # Create indexes
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rca_incident_id 
            ON rca_analyses(incident_id)
            """)
            
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rca_endpoint 
            ON rca_analyses(endpoint)
            """)
            
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rca_timestamp 
            ON rca_analyses(created_at)
            """)
            
            self.db_connection.commit()
            log.info("RCA tables created/verified")
            
        except Exception as e:
            log.error("Table creation failed", error=str(e))
            self.db_connection.rollback()
    
    def _load_incident_history(self):
        """Load historical incidents from database"""
        if not self.db_connection:
            return
        
        try:
            cursor = self.db_connection.cursor(cursor_factory=RealDictCursor)
            
            # Load last 1000 incidents
            cursor.execute("""
            SELECT 
                incident_id,
                endpoint,
                anomalous_metric,
                root_causes,
                recommendations,
                ttd_seconds,
                analysis_time
            FROM rca_analyses
            ORDER BY analysis_time DESC
            LIMIT 1000
            """)
            
            for row in cursor.fetchall():
                endpoint = row['endpoint']
                self.incident_history[endpoint].append({
                    'incident_id': row['incident_id'],
                    'metric': row['anomalous_metric'],
                    'root_causes': json.loads(row['root_causes']),
                    'recommendations': row['recommendations'],
                    'ttd_seconds': row['ttd_seconds'],
                    'timestamp': row['analysis_time']
                })
            
            log.info(
                "Incident history loaded",
                endpoints_loaded=len(self.incident_history)
            )
            
        except Exception as e:
            log.warning("Failed to load incident history", error=str(e))
    
    async def _consume_anomalies(self):
        """Consume anomalies from Kafka and perform RCA"""
        if not self.kafka_consumer:
            log.error("Kafka consumer not initialized")
            return
        
        log.info("Starting anomaly consumption")
        
        try:
            for message in self.kafka_consumer:
                anomaly = message.value
                log.info("Processing anomaly", incident_id=anomaly.get('incident_id'))
                
                # Perform RCA
                rca_result = await self._analyze_anomaly(anomaly)
                
                if rca_result:
                    # Store in database
                    self._store_rca_result(rca_result)
                    
                    # Publish to Kafka
                    await self._publish_rca_result(rca_result)
                    
                    log.info(
                        "RCA completed",
                        incident_id=rca_result.incident_id,
                        root_causes=len(rca_result.root_causes)
                    )
        
        except Exception as e:
            log.error("Anomaly consumption failed", error=str(e))
    
    async def _analyze_anomaly(self, anomaly: Dict) -> Optional[RCAResult]:
        """
        Perform RCA on anomaly
        
        Args:
            anomaly: Anomaly data from Kafka
            
        Returns:
            RCAResult or None
        """
        try:
            incident_id = anomaly.get('incident_id')
            endpoint = anomaly.get('endpoint', 'unknown')
            timestamp = datetime.fromisoformat(anomaly.get('timestamp', datetime.utcnow().isoformat()))
            anomalous_metric = anomaly.get('metric_name', 'unknown')
            anomalous_value = anomaly.get('value', 0)
            baseline_value = anomaly.get('baseline', 0)
            severity = anomaly.get('severity', 'MEDIUM')
            
            # Get historical metrics (from feature store)
            metrics_df = await self._fetch_metrics_data(endpoint, timestamp)
            
            if metrics_df is None or len(metrics_df) < 20:
                log.warning("Insufficient metrics data", incident_id=incident_id)
                return None
            
            # 1. Correlation Analysis
            correlated = self.correlation_engine.find_correlated_metrics(
                anomalous_metric, endpoint, min_correlation=0.5
            )
            
            # 2. Causal Analysis
            causal_graph = self.causal_analyzer.discover_causal_relationships(
                list(metrics_df.columns), metrics_df, min_confidence=0.3
            )
            
            # Classify metrics using causal graph
            metric_findings = self.causal_analyzer.propagate_anomaly(
                causal_graph,
                anomalous_metric,
                [c.metric_1 for c in correlated] + [anomalous_metric]
            )
            
            # 3. Service Dependency Analysis
            service_deps = self.dependency_analyzer.get_downstream_services(
                endpoint.split(':')[0] if ':' in endpoint else endpoint
            )
            
            cascade_risks = self.dependency_analyzer.detect_cascade_failures()
            
            # 4. Historical Incident Matching
            similar_incidents = self._find_similar_incidents(
                endpoint, anomalous_metric
            )
            
            # Build RCA Result
            root_causes = [
                RCAMetricContribution(
                    metric_name=rel.cause_metric,
                    deviation_percentage=(
                        abs(anomalous_value - baseline_value) / (baseline_value + 1e-6) * 100
                    ),
                    finding_type=metric_findings.get(rel.cause_metric, RCAFinding.CONTRIBUTING_FACTOR),
                    evidence=f"Causal relationship with {rel.effect_metric}"
                )
                for rel in causal_graph.relationships
                if rel.cause_metric == anomalous_metric
            ]
            
            if not root_causes:
                root_causes = [
                    RCAMetricContribution(
                        metric_name=anomalous_metric,
                        deviation_percentage=(
                            abs(anomalous_value - baseline_value) / (baseline_value + 1e-6) * 100
                        ),
                        finding_type=RCAFinding.ROOT_CAUSE,
                        evidence="Direct anomaly detection"
                    )
                ]
            
            contributing_factors = [
                RCAMetricContribution(
                    metric_name=corr.metric_2,
                    deviation_percentage=5.0,  # Placeholder
                    finding_type=RCAFinding.CONTRIBUTING_FACTOR,
                    evidence=f"Correlation: {corr.correlation_coefficient:.2f}"
                )
                for corr in correlated[:3]
            ]
            
            symptoms = [
                RCAMetricContribution(
                    metric_name=rel.effect_metric,
                    deviation_percentage=3.0,
                    finding_type=RCAFinding.SYMPTOM,
                    evidence=f"Downstream effect from {rel.cause_metric}"
                )
                for rel in causal_graph.relationships
                if rel.cause_metric == anomalous_metric
            ]
            
            # Generate recommendations
            recommendations = self._generate_recommendations(
                anomalous_metric,
                root_causes,
                similar_incidents,
                service_deps
            )
            
            # Calculate confidence
            confidence = (
                (len(causal_graph.relationships) * 0.3 +
                 len(correlated) * 0.2 +
                 len(similar_incidents) * 0.5) / max(1, len(correlated) + len(causal_graph.relationships))
            )
            confidence = min(1.0, confidence)
            
            rca_result = RCAResult(
                incident_id=incident_id,
                endpoint=endpoint,
                anomalous_metric=anomalous_metric,
                root_causes=root_causes,
                contributing_factors=contributing_factors,
                symptoms=symptoms,
                evidence={
                    'correlation_count': len(correlated),
                    'causal_relationships': len(causal_graph.relationships),
                    'similar_incidents': len(similar_incidents),
                    'cascade_risk': len(service_deps) > 0
                },
                recommendations=recommendations,
                confidence=confidence,
                analysis_timestamp=datetime.utcnow()
            )
            
            return rca_result
            
        except Exception as e:
            log.error("RCA analysis failed", incident_id=incident_id, error=str(e))
            return None
    
    async def _fetch_metrics_data(
        self,
        endpoint: str,
        timestamp: datetime,
        lookback_seconds: int = 900
    ) -> Optional[pd.DataFrame]:
        """
        Fetch metrics data for analysis
        
        Args:
            endpoint: Endpoint to fetch metrics for
            timestamp: Reference timestamp
            lookback_seconds: How far back to fetch
            
        Returns:
            DataFrame with metric time series
        """
        # TODO: Implement metrics fetching from TimescaleDB
        # For now, return mock data
        import numpy as np
        
        data = {}
        metrics = ['latency_ms', 'cpu_percent', 'memory_mb', 'throughput_rps', 'error_rate']
        
        for metric in metrics:
            base = np.random.normal(50, 10)
            data[metric] = np.random.normal(base, 5, 100)
        
        return pd.DataFrame(data)
    
    def _find_similar_incidents(
        self,
        endpoint: str,
        metric: str,
        similarity_threshold: float = 0.7
    ) -> List[HistoricalIncidentMatch]:
        """
        Find similar historical incidents
        
        Args:
            endpoint: Endpoint
            metric: Anomalous metric
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of similar incidents
        """
        similar = []
        
        if endpoint not in self.incident_history:
            return similar
        
        for incident in self.incident_history[endpoint][-100:]:  # Check last 100
            if incident['metric'] == metric:
                # High similarity for same metric
                similarity = 0.9
            else:
                similarity = 0.5
            
            if similarity >= similarity_threshold:
                match = HistoricalIncidentMatch(
                    incident_id=incident['incident_id'],
                    similarity_score=similarity,
                    resolution_summary=incident['recommendations'],
                    time_to_mitigation_seconds=incident.get('ttd_seconds', 300)
                )
                similar.append(match)
        
        return similar[:3]  # Return top 3
    
    def _generate_recommendations(
        self,
        metric: str,
        root_causes: List,
        similar_incidents: List,
        service_deps: List
    ) -> str:
        """Generate recommendations"""
        recs = []
        
        if root_causes:
            recs.append(f"Primary focus: Investigate {root_causes[0].metric_name}")
        
        if similar_incidents:
            recs.append(
                f"Similar incident resolution: {similar_incidents[0].resolution_summary}"
            )
        
        if service_deps:
            recs.append(
                f"Check cascade impact on {len(service_deps)} downstream services"
            )
        
        recs.append("Correlate metrics to identify contributing factors")
        
        return " | ".join(recs)
    
    def _store_rca_result(self, rca_result: RCAResult):
        """Store RCA result in database"""
        if not self.db_connection:
            return
        
        try:
            cursor = self.db_connection.cursor()
            
            cursor.execute("""
            INSERT INTO rca_analyses (
                incident_id, endpoint, anomalous_metric,
                root_causes, contributing_factors, symptoms,
                evidence, recommendations, confidence
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (incident_id) DO UPDATE SET
                root_causes = EXCLUDED.root_causes,
                contributing_factors = EXCLUDED.contributing_factors,
                symptoms = EXCLUDED.symptoms,
                evidence = EXCLUDED.evidence,
                recommendations = EXCLUDED.recommendations,
                confidence = EXCLUDED.confidence
            """, (
                rca_result.incident_id,
                rca_result.endpoint,
                rca_result.anomalous_metric,
                json.dumps([rc.to_dict() for rc in rca_result.root_causes]),
                json.dumps([cf.to_dict() for cf in rca_result.contributing_factors]),
                json.dumps([s.to_dict() for s in rca_result.symptoms]),
                json.dumps(rca_result.evidence),
                rca_result.recommendations,
                rca_result.confidence
            ))
            
            self.db_connection.commit()
            log.info("RCA result stored", incident_id=rca_result.incident_id)
            
        except Exception as e:
            log.error("Failed to store RCA result", error=str(e))
            self.db_connection.rollback()
    
    async def _publish_rca_result(self, rca_result: RCAResult):
        """Publish RCA result to Kafka"""
        if not self.kafka_producer:
            return
        
        try:
            message = {
                'incident_id': rca_result.incident_id,
                'endpoint': rca_result.endpoint,
                'root_causes': [rc.to_dict() for rc in rca_result.root_causes],
                'contributing_factors': [cf.to_dict() for cf in rca_result.contributing_factors],
                'symptoms': [s.to_dict() for s in rca_result.symptoms],
                'recommendations': rca_result.recommendations,
                'confidence': rca_result.confidence,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            self.kafka_producer.send('root-causes', value=message)
            log.info("RCA published to Kafka", incident_id=rca_result.incident_id)
            
        except Exception as e:
            log.error("Failed to publish RCA result", error=str(e))
    
    def shutdown(self):
        """Shutdown the service"""
        if self.kafka_consumer:
            self.kafka_consumer.close()
        
        if self.kafka_producer:
            self.kafka_producer.close()
        
        if self.db_connection:
            self.db_connection.close()
        
        log.info("RCA Service shutdown complete")


async def main():
    """Main entry point"""
    service = RCAService()
    
    try:
        await service.start()
    except KeyboardInterrupt:
        log.info("Shutdown signal received")
        service.shutdown()
    except Exception as e:
        log.error("Fatal error", error=str(e))
        service.shutdown()
        raise


if __name__ == '__main__':
    asyncio.run(main())
