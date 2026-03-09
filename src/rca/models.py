"""
Root Cause Analysis Data Models

Data structures for RCA analysis:
- Correlation results
- Service dependencies
- Causal relationships
- RCA findings
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum
import json


class CorrelationType(str, Enum):
    """Types of metric correlation"""
    STRONG_POSITIVE = "strong_positive"    # corr > 0.7
    MODERATE_POSITIVE = "moderate_positive"  # 0.5-0.7
    WEAK_POSITIVE = "weak_positive"        # 0.3-0.5
    WEAK_NEGATIVE = "weak_negative"        # -0.5 to -0.3
    MODERATE_NEGATIVE = "moderate_negative"  # -0.7 to -0.5
    STRONG_NEGATIVE = "strong_negative"    # corr < -0.7
    NO_CORRELATION = "no_correlation"      # -0.3 to 0.3


class CausalityConfidence(str, Enum):
    """Confidence in causal relationship"""
    HIGH = "high"        # >80% confidence
    MEDIUM = "medium"    # 50-80%
    LOW = "low"          # 20-50%
    INSUFFICIENT = "insufficient"  # <20%


class RCAFinding(str, Enum):
    """Types of RCA findings"""
    ROOT_CAUSE = "root_cause"              # Likely root cause
    CONTRIBUTING_FACTOR = "contributing_factor"  # Contributes to issue
    SYMPTOM = "symptom"                    # Consequence of root cause
    UNRELATED = "unrelated"                # Not related


# ============================================================================
# Correlation Models
# ============================================================================

@dataclass
class MetricCorrelation:
    """Correlation between two metrics"""
    metric_1: str
    metric_2: str
    endpoint: str
    correlation_coefficient: float  # -1 to 1
    correlation_type: CorrelationType
    sample_count: int
    p_value: float  # Statistical significance
    lag_offset: int  # Time lag in seconds (0 = simultaneous)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            'metric_1': self.metric_1,
            'metric_2': self.metric_2,
            'endpoint': self.endpoint,
            'correlation_coefficient': float(self.correlation_coefficient),
            'correlation_type': self.correlation_type.value,
            'sample_count': self.sample_count,
            'p_value': float(self.p_value),
            'lag_offset': self.lag_offset,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class CorrelationSnapshot:
    """Correlations at specific time"""
    timestamp: datetime
    endpoint: str
    correlations: List[MetricCorrelation] = field(default_factory=list)
    analysis_window_seconds: int = 300  # 5 minutes
    
    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'endpoint': self.endpoint,
            'correlations': [c.to_dict() for c in self.correlations],
            'analysis_window_seconds': self.analysis_window_seconds
        }


# ============================================================================
# Service Dependency Models
# ============================================================================

@dataclass
class ServiceDependency:
    """Dependency relationship between services"""
    source_service: str
    target_service: str
    dependency_type: str  # calls, depends_on, publishes_to, etc.
    confidence: float  # 0-1, based on call frequency
    average_latency_ms: float
    call_volume_per_min: float
    error_rate: float
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            'source': self.source_service,
            'target': self.target_service,
            'type': self.dependency_type,
            'confidence': float(self.confidence),
            'avg_latency_ms': float(self.average_latency_ms),
            'calls_per_min': float(self.call_volume_per_min),
            'error_rate': float(self.error_rate),
            'last_updated': self.last_updated.isoformat()
        }


@dataclass
class DependencyGraph:
    """Complete service dependency graph"""
    timestamp: datetime
    services: List[str]
    dependencies: List[ServiceDependency] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'services': self.services,
            'dependencies': [d.to_dict() for d in self.dependencies]
        }
    
    def get_upstream_services(self, service_name: str) -> List[str]:
        """Get services that call this service"""
        upstream = []
        for dep in self.dependencies:
            if dep.target_service == service_name:
                upstream.append(dep.source_service)
        return upstream
    
    def get_downstream_services(self, service_name: str) -> List[str]:
        """Get services this service calls"""
        downstream = []
        for dep in self.dependencies:
            if dep.source_service == service_name:
                downstream.append(dep.target_service)
        return downstream
    
    def get_critical_path(self, service_name: str) -> List[str]:
        """Get dependency chain that affects this service"""
        visited = set()
        path = []
        
        def dfs(current: str):
            if current in visited:
                return
            visited.add(current)
            path.append(current)
            
            for dep in self.dependencies:
                if dep.target_service == current and dep.confidence > 0.7:
                    dfs(dep.source_service)
        
        dfs(service_name)
        return path


# ============================================================================
# Causal Inference Models
# ============================================================================

@dataclass
class CausalRelationship:
    """Causal relationship between metrics"""
    cause_metric: str
    effect_metric: str
    endpoint: str
    confidence: CausalityConfidence
    treatment_effect: float  # Estimated change in effect from cause
    backdoor_adjustment: bool  # Whether confounders were controlled
    causal_method: str  # "propensity_score", "backdoor", "frontdoor", etc.
    supporting_evidence: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            'cause': self.cause_metric,
            'effect': self.effect_metric,
            'endpoint': self.endpoint,
            'confidence': self.confidence.value,
            'treatment_effect': float(self.treatment_effect),
            'backdoor_adjustment': self.backdoor_adjustment,
            'causal_method': self.causal_method,
            'supporting_evidence': self.supporting_evidence,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class CausalGraph:
    """Directed acyclic graph of causal relationships"""
    timestamp: datetime
    endpoint: str
    relationships: List[CausalRelationship] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'endpoint': self.endpoint,
            'relationships': [r.to_dict() for r in self.relationships]
        }
    
    def find_root_causes(self) -> List[str]:
        """Find metrics with no incoming relationships (root causes)"""
        effects = set(r.effect_metric for r in self.relationships)
        causes = set(r.cause_metric for r in self.relationships)
        return list(causes - effects)  # Metrics that are causes but not effects
    
    def get_causality_chain(self, effect_metric: str) -> List[List[str]]:
        """Get all causal chains leading to this metric"""
        chains = []
        
        def dfs(current: str, path: List[str]):
            # Find causes of current metric
            causes = [r.cause_metric for r in self.relationships 
                     if r.effect_metric == current and r.confidence != CausalityConfidence.INSUFFICIENT]
            
            if not causes:
                chains.append(path)
                return
            
            for cause in causes:
                dfs(cause, [cause] + path)
        
        dfs(effect_metric, [effect_metric])
        return chains


# ============================================================================
# RCA Result Models
# ============================================================================

@dataclass
class RCAMetricContribution:
    """Contribution of metric to anomaly"""
    metric_name: str
    anomaly_score: float  # 0-1
    baseline_value: float
    anomalous_value: float
    deviation_percentage: float
    finding_type: RCAFinding
    confidence: float  # 0-1
    
    def to_dict(self) -> dict:
        return {
            'metric': self.metric_name,
            'anomaly_score': float(self.anomaly_score),
            'baseline': float(self.baseline_value),
            'anomalous': float(self.anomalous_value),
            'deviation_percent': float(self.deviation_percentage),
            'type': self.finding_type.value,
            'confidence': float(self.confidence)
        }


@dataclass
class RCAResult:
    """Root Cause Analysis result"""
    rca_id: str
    timestamp: datetime
    incident_id: str
    endpoint: str
    
    # Root causes and contributing factors
    root_causes: List[RCAMetricContribution] = field(default_factory=list)
    contributing_factors: List[RCAMetricContribution] = field(default_factory=list)
    symptoms: List[RCAMetricContribution] = field(default_factory=list)
    
    # Evidence
    correlation_evidence: List[MetricCorrelation] = field(default_factory=list)
    causal_evidence: List[CausalRelationship] = field(default_factory=list)
    dependency_evidence: List[ServiceDependency] = field(default_factory=list)
    
    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    runbook_urls: List[str] = field(default_factory=list)
    
    # Confidence
    overall_confidence: float = 0.5  # 0-1
    analysis_complete: bool = False
    
    def to_dict(self) -> dict:
        return {
            'rca_id': self.rca_id,
            'timestamp': self.timestamp.isoformat(),
            'incident_id': self.incident_id,
            'endpoint': self.endpoint,
            'root_causes': [rc.to_dict() for rc in self.root_causes],
            'contributing_factors': [cf.to_dict() for cf in self.contributing_factors],
            'symptoms': [s.to_dict() for s in self.symptoms],
            'correlation_evidence': [c.to_dict() for c in self.correlation_evidence],
            'causal_evidence': [c.to_dict() for c in self.causal_evidence],
            'dependency_evidence': [d.to_dict() for d in self.dependency_evidence],
            'recommendations': self.recommendations,
            'runbook_urls': self.runbook_urls,
            'overall_confidence': float(self.overall_confidence),
            'analysis_complete': self.analysis_complete
        }


@dataclass
class HistoricalIncidentMatch:
    """Similar incident found in history"""
    previous_incident_id: str
    similarity_score: float  # 0-1
    matched_metrics: List[str]
    resolution: Optional[str]
    confirmed_root_cause: Optional[str]
    ttm_minutes: int  # Time to mitigation
    
    def to_dict(self) -> dict:
        return {
            'previous_incident_id': self.previous_incident_id,
            'similarity_score': float(self.similarity_score),
            'matched_metrics': self.matched_metrics,
            'resolution': self.resolution,
            'root_cause': self.confirmed_root_cause,
            'ttm_minutes': self.ttm_minutes
        }
