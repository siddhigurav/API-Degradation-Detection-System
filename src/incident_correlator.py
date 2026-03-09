"""
Advanced Incident Correlation

Correlates incidents across services to identify:
- Root incident vs secondary incidents
- Cascade effects
- Pattern detection
- Temporal correlations
"""

from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple, Optional
import logging

log = logging.getLogger(__name__)


class IncidentRelation:
    """Relationship between incidents"""
    
    def __init__(
        self,
        incident_a_id: str,
        incident_b_id: str,
        relation_type: str,
        confidence: float,
        evidence: List[str]
    ):
        self.incident_a_id = incident_a_id
        self.incident_b_id = incident_b_id
        self.relation_type = relation_type  # "causes", "coincident", "cascade"
        self.confidence = confidence  # 0-1
        self.evidence = evidence
        self.discovered_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "incident_a": self.incident_a_id,
            "incident_b": self.incident_b_id,
            "relation_type": self.relation_type,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "discovered_at": self.discovered_at.isoformat()
        }


class IncidentCluster:
    """Cluster of related incidents"""
    
    def __init__(self, cluster_id: str):
        self.cluster_id = cluster_id
        self.incidents: Set[str] = set()
        self.root_incident: Optional[str] = None
        self.secondary_incidents: Set[str] = set()
        self.cascade_chain: List[str] = []  # Ordered chain: root -> secondary -> secondary
        self.created_at = datetime.utcnow()
        self.resolved_at: Optional[datetime] = None
        self.total_impact_score = 0.0
        self.patterns: List[str] = []
    
    def add_incident(self, incident_id: str, is_root: bool = False):
        """Add incident to cluster"""
        self.incidents.add(incident_id)
        
        if is_root:
            self.root_incident = incident_id
        else:
            self.secondary_incidents.add(incident_id)
    
    def set_cascade_chain(self, chain: List[str]):
        """Set the cascade chain (temporal order)"""
        self.cascade_chain = chain
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "cluster_id": self.cluster_id,
            "incidents": list(self.incidents),
            "root_incident": self.root_incident,
            "secondary_incidents": list(self.secondary_incidents),
            "cascade_chain": self.cascade_chain,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "total_impact_score": self.total_impact_score,
            "patterns": self.patterns
        }


class CorrelationEngine:
    """Correlate incidents across services"""
    
    def __init__(self):
        """Initialize correlation engine"""
        self.incidents: Dict[str, Dict] = {}
        self.relations: List[IncidentRelation] = []
        self.clusters: Dict[str, IncidentCluster] = {}
        self.patterns: Dict[str, List[str]] = {}
    
    def register_incident(
        self,
        incident_id: str,
        service: str,
        endpoint: str,
        metric_name: str,
        severity: str,
        timestamp: datetime,
        metric_value: float,
        recent_context: Dict = None
    ):
        """Register incident for correlation"""
        
        self.incidents[incident_id] = {
            "service": service,
            "endpoint": endpoint,
            "metric_name": metric_name,
            "severity": severity,
            "timestamp": timestamp,
            "metric_value": metric_value,
            "context": recent_context or {},
            "registered_at": datetime.utcnow()
        }
        
        log.info(f"Registered incident: {incident_id}")
    
    def correlate_incidents(self) -> List[IncidentCluster]:
        """Find correlations between incidents"""
        
        incident_ids = list(self.incidents.keys())
        new_clusters = []
        
        for i, inc_a in enumerate(incident_ids):
            for inc_b in incident_ids[i+1:]:
                confidence, relation_type = self._calculate_correlation(inc_a, inc_b)
                
                if confidence > 0.5:  # Threshold
                    evidence = self._gather_evidence(inc_a, inc_b)
                    
                    relation = IncidentRelation(
                        incident_a_id=inc_a,
                        incident_b_id=inc_b,
                        relation_type=relation_type,
                        confidence=confidence,
                        evidence=evidence
                    )
                    
                    self.relations.append(relation)
                    
                    # Create or update cluster
                    cluster = self._cluster_incidents(inc_a, inc_b, relation)
                    if cluster:
                        new_clusters.append(cluster)
                    
                    log.info(
                        f"Correlation found: {inc_a} -> {inc_b} "
                        f"({relation_type}, confidence={confidence:.2f})"
                    )
        
        return new_clusters
    
    def _calculate_correlation(
        self,
        incident_a: str,
        incident_b: str
    ) -> Tuple[float, str]:
        """Calculate correlation between two incidents"""
        
        a = self.incidents[incident_a]
        b = self.incidents[incident_b]
        
        # 1. Temporal correlation
        time_diff = abs(
            (a["timestamp"] - b["timestamp"]).total_seconds()
        )
        
        if time_diff > 300:  # > 5 minutes apart
            temporal_score = 0.0
        elif time_diff < 5:  # < 5 seconds apart
            temporal_score = 0.9
        else:
            temporal_score = 1.0 - (time_diff / 300)
        
        # 2. Service dependency correlation
        service_a = a["service"]
        service_b = b["service"]
        
        # Check if services are related
        dependency_score = self._check_service_dependency(service_a, service_b)
        
        # 3. Metric similarity
        metric_similarity = 1.0 if a["metric_name"] == b["metric_name"] else 0.3
        
        # 4. Severity correlation
        severity_score = 0.8 if a["severity"] == b["severity"] else 0.3
        
        # Weighted combination
        overall_confidence = (
            temporal_score * 0.4 +
            dependency_score * 0.3 +
            metric_similarity * 0.2 +
            severity_score * 0.1
        )
        
        # Determine relation type
        if temporal_score > 0.7 and dependency_score > 0.6:
            # A likely caused B
            if (a["timestamp"] < b["timestamp"]):
                relation_type = "causes"
            else:
                relation_type = "caused_by"
        elif a["service"] != b["service"] and temporal_score > 0.7:
            relation_type = "cascade"
        else:
            relation_type = "coincident"
        
        return overall_confidence, relation_type
    
    def _check_service_dependency(self, service_a: str, service_b: str) -> float:
        """Check if services are dependent"""
        
        # Common dependencies
        dependencies = {
            "api_gateway": ["auth_service", "rate_limit_service"],
            "auth_service": ["database"],
            "api_server": ["database", "cache", "kafka"],
            "database": [],
            "cache": ["database"],
            "kafka": ["database"],
        }
        
        # Check both directions
        a_depends_on_b = service_b in dependencies.get(service_a, [])
        b_depends_on_a = service_a in dependencies.get(service_b, [])
        
        if a_depends_on_b or b_depends_on_a:
            return 0.9
        
        return 0.2  # Services in same system
    
    def _gather_evidence(self, incident_a: str, incident_b: str) -> List[str]:
        """Gather evidence for correlation"""
        
        a = self.incidents[incident_a]
        b = self.incidents[incident_b]
        
        evidence = []
        
        # Temporal evidence
        time_diff = abs((a["timestamp"] - b["timestamp"]).total_seconds())
        if time_diff < 10:
            evidence.append(f"Occurred within {int(time_diff)}s")
        
        # Service evidence
        if a["service"] in ["api_server"] and b["service"] in ["database"]:
            evidence.append("Database is upstream of API")
        
        # Metric evidence
        if a["metric_name"] == b["metric_name"]:
            evidence.append(f"Same metric affected: {a['metric_name']}")
        
        # Severity evidence
        if a["severity"] == b["severity"]:
            evidence.append(f"Same severity: {a['severity']}")
        
        # Value correlation
        if abs(a["metric_value"] - b["metric_value"]) < 10:
            evidence.append("Comparable metric values")
        
        return evidence
    
    def _cluster_incidents(
        self,
        inc_a: str,
        inc_b: str,
        relation: IncidentRelation
    ) -> Optional[IncidentCluster]:
        """Create or update cluster"""
        
        # Find existing clusters containing these incidents
        cluster_a = None
        cluster_b = None
        
        for cluster in self.clusters.values():
            if inc_a in cluster.incidents:
                cluster_a = cluster
            if inc_b in cluster.incidents:
                cluster_b = cluster
        
        # Merge clusters or create new
        if cluster_a and cluster_b and cluster_a != cluster_b:
            # Merge clusters
            cluster_a.incidents.update(cluster_b.incidents)
            cluster_a.secondary_incidents.update(cluster_b.secondary_incidents)
            del self.clusters[cluster_b.cluster_id]
            return cluster_a
        
        if cluster_a:
            # Add to existing cluster
            cluster_a.add_incident(inc_b, is_root=False)
            return cluster_a
        
        if cluster_b:
            # Add to existing cluster
            cluster_b.add_incident(inc_a, is_root=False)
            return cluster_b
        
        # Create new cluster
        cluster = IncidentCluster(
            cluster_id=f"cluster_{inc_a[:8]}_{inc_b[:8]}"
        )
        
        if relation.relation_type == "causes":
            cluster.add_incident(inc_a, is_root=True)
            cluster.add_incident(inc_b, is_root=False)
        elif relation.relation_type == "caused_by":
            cluster.add_incident(inc_b, is_root=True)
            cluster.add_incident(inc_a, is_root=False)
        else:
            cluster.add_incident(inc_a, is_root=True)
            cluster.add_incident(inc_b, is_root=False)
        
        self.clusters[cluster.cluster_id] = cluster
        return cluster
    
    def analyze_cascade_effects(self, cluster_id: str) -> List[Tuple[str, str, float]]:
        """Analyze cascade effects in cluster"""
        
        cluster = self.clusters.get(cluster_id)
        if not cluster:
            return []
        
        # Build causality graph
        cascade = []
        
        for relation in self.relations:
            if (relation.incident_a_id in cluster.incidents and
                relation.incident_b_id in cluster.incidents):
                
                if relation.relation_type in ["causes", "cascade"]:
                    cascade.append((
                        relation.incident_a_id,
                        relation.incident_b_id,
                        relation.confidence
                    ))
        
        # Order by temporal sequence
        cascade = sorted(cascade, key=lambda x: x[2], reverse=True)
        cluster.cascade_chain = [x[0] for x in cascade] + [cascade[-1][1]] if cascade else []
        
        return cascade
    
    def detect_patterns(self) -> Dict[str, List[str]]:
        """Detect recurring incident patterns"""
        
        # Group incidents by service and metric
        patterns_found = {}
        
        by_service_metric = {}
        for inc_id, inc_data in self.incidents.items():
            key = f"{inc_data['service']}:{inc_data['metric_name']}"
            if key not in by_service_metric:
                by_service_metric[key] = []
            by_service_metric[key].append(inc_id)
        
        # Find patterns (3+ incidents in same category)
        for key, incidents in by_service_metric.items():
            if len(incidents) >= 3:
                pattern_name = f"recurring_{key.replace(':', '_')}"
                patterns_found[pattern_name] = incidents
                
                for cluster_id in self.clusters:
                    for inc in incidents:
                        if inc in self.clusters[cluster_id].incidents:
                            self.clusters[cluster_id].patterns.append(pattern_name)
        
        self.patterns = patterns_found
        return patterns_found
    
    def get_cluster_summary(self, cluster_id: str) -> Dict:
        """Get cluster summary"""
        
        cluster = self.clusters.get(cluster_id)
        if not cluster:
            return {}
        
        return {
            "cluster_id": cluster_id,
            "incidents": list(cluster.incidents),
            "incident_count": len(cluster.incidents),
            "root_incident": cluster.root_incident,
            "cascade_chain": cluster.cascade_chain,
            "patterns": cluster.patterns,
            "created_at": cluster.created_at.isoformat(),
            "duration_minutes": (datetime.utcnow() - cluster.created_at).total_seconds() / 60
        }
    
    def get_all_clusters(self) -> List[Dict]:
        """Get all clusters"""
        return [
            cluster.to_dict()
            for cluster in self.clusters.values()
        ]


# Global correlation engine
correlation_engine = CorrelationEngine()
