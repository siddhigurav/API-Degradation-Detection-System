"""
Service Dependency Analyzer

Builds service dependency graphs from traces and metrics.
Detects service-to-service relationships and identifies cascade failures.
"""

import pandas as pd
import networkx as nx
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict
import structlog

from src.rca.models import (
    ServiceDependency, DependencyGraph
)

log = structlog.get_logger()


class DependencyAnalyzer:
    """Analyzes and builds service dependency graphs"""
    
    def __init__(self):
        """Initialize dependency analyzer"""
        self.service_calls = defaultdict(lambda: defaultdict(list))  # {source: {target: [call_records]}}
        self.dependency_graph = None
        
    def record_service_call(
        self,
        source_service: str,
        target_service: str,
        latency_ms: float,
        success: bool,
        timestamp: datetime
    ):
        """
        Record a service call
        
        Args:
            source_service: Calling service
            target_service: Called service
            latency_ms: Call latency in milliseconds
            success: Whether call succeeded
            timestamp: Call time
        """
        call_record = {
            'timestamp': timestamp,
            'latency_ms': latency_ms,
            'success': success
        }
        
        self.service_calls[source_service][target_service].append(call_record)
        
        # Keep only recent calls (last 1 hour)
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self.service_calls[source_service][target_service] = [
            c for c in self.service_calls[source_service][target_service]
            if c['timestamp'] >= cutoff
        ]
    
    def compute_call_statistics(
        self,
        source_service: str,
        target_service: str,
        time_window_seconds: int = 300
    ) -> Dict:
        """
        Compute statistics for service calls
        
        Args:
            source_service: Source service
            target_service: Target service
            time_window_seconds: Time window for analysis
            
        Returns:
            Statistics dict with call volume, latency, error rate
        """
        cutoff = datetime.utcnow() - timedelta(seconds=time_window_seconds)
        
        calls = [
            c for c in self.service_calls[source_service][target_service]
            if c['timestamp'] >= cutoff
        ]
        
        if not calls:
            return {
                'call_count': 0,
                'avg_latency_ms': 0,
                'p95_latency_ms': 0,
                'p99_latency_ms': 0,
                'error_rate': 0,
                'success_count': 0,
                'failure_count': 0
            }
        
        latencies = [c['latency_ms'] for c in calls]
        success_calls = [c for c in calls if c['success']]
        
        return {
            'call_count': len(calls),
            'avg_latency_ms': sum(latencies) / len(latencies),
            'p95_latency_ms': float(pd.Series(latencies).quantile(0.95)),
            'p99_latency_ms': float(pd.Series(latencies).quantile(0.99)),
            'error_rate': 1.0 - (len(success_calls) / len(calls)),
            'success_count': len(success_calls),
            'failure_count': len(calls) - len(success_calls)
        }
    
    def build_dependency_graph(self) -> DependencyGraph:
        """
        Build service dependency graph
        
        Returns:
            DependencyGraph with discovered dependencies
        """
        dependencies = []
        
        # Build from recorded calls
        for source_service, targets in self.service_calls.items():
            for target_service, calls in targets.items():
                if not calls:
                    continue
                
                # Compute statistics
                stats = self.compute_call_statistics(source_service, target_service)
                
                # Only include if sufficient calls
                if stats['call_count'] >= 5:
                    dep = ServiceDependency(
                        source_service=source_service,
                        target_service=target_service,
                        call_volume=stats['call_count'],
                        avg_latency_ms=stats['avg_latency_ms'],
                        p95_latency_ms=stats['p95_latency_ms'],
                        error_rate=stats['error_rate'],
                        timestamp=datetime.utcnow()
                    )
                    dependencies.append(dep)
        
        graph = DependencyGraph(
            dependencies=dependencies,
            timestamp=datetime.utcnow()
        )
        
        self.dependency_graph = graph
        return graph
    
    def get_critical_path(self, service: str) -> Optional[List[str]]:
        """
        Get critical path through service dependencies
        
        Args:
            service: Service to analyze
            
        Returns:
            List of services in critical path (highest latency)
        """
        if not self.dependency_graph:
            return None
        
        return self.dependency_graph.get_critical_path(service)
    
    def get_upstream_services(self, service: str) -> List[str]:
        """
        Get services that call this service
        
        Args:
            service: Target service
            
        Returns:
            List of upstream services
        """
        if not self.dependency_graph:
            return []
        
        return [
            dep.source_service for dep in self.dependency_graph.dependencies
            if dep.target_service == service
        ]
    
    def get_downstream_services(self, service: str) -> List[str]:
        """
        Get services called by this service
        
        Args:
            service: Source service
            
        Returns:
            List of downstream services
        """
        if not self.dependency_graph:
            return []
        
        return [
            dep.target_service for dep in self.dependency_graph.dependencies
            if dep.source_service == service
        ]
    
    def detect_cascade_failures(self) -> Dict[str, Dict]:
        """
        Detect potential cascade failure scenarios
        
        Returns:
            Dict mapping service to cascade risk analysis
        """
        if not self.dependency_graph:
            self.build_dependency_graph()
        
        cascade_risks = {}
        
        for dep in self.dependency_graph.dependencies:
            source = dep.source_service
            target = dep.target_service
            
            # Risk score based on error rate and downstream impact
            error_risk = min(1.0, dep.error_rate * 2)  # Scale error rate
            
            # Check downstream impact
            downstream = self.get_downstream_services(target)
            downstream_count = len(downstream)
            
            # Impact score
            impact_score = min(1.0, downstream_count / 10.0)
            
            # Combined risk
            risk_score = (error_risk + impact_score) / 2
            
            if source not in cascade_risks:
                cascade_risks[source] = {
                    'direct_targets': [],
                    'overall_risk': 0
                }
            
            cascade_risks[source]['direct_targets'].append({
                'target': target,
                'error_rate': dep.error_rate,
                'downstream_services': downstream,
                'cascade_risk': risk_score
            })
        
        # Calculate overall risk
        for service, risks in cascade_risks.items():
            overall = sum(t['cascade_risk'] for t in risks['direct_targets']) / max(1, len(risks['direct_targets']))
            risks['overall_risk'] = overall
        
        return cascade_risks
    
    def measure_latency_impact(
        self,
        source_service: str,
        target_service: str
    ) -> Dict:
        """
        Measure latency impact of slow service
        
        Args:
            source_service: Service making call
            target_service: Service being called
            
        Returns:
            Impact analysis
        """
        stats = self.compute_call_statistics(source_service, target_service)
        
        # Get downstream services affected by latency
        downstream = self.get_downstream_services(target_service)
        
        return {
            'source': source_service,
            'target': target_service,
            'current_latency': stats['avg_latency_ms'],
            'p95_latency': stats['p95_latency_ms'],
            'p99_latency': stats['p99_latency_ms'],
            'downstream_services': downstream,
            'downstream_count': len(downstream),
            'call_volume': stats['call_count']
        }
    
    def measure_error_propagation(
        self,
        source_service: str,
        target_service: str
    ) -> Dict:
        """
        Measure error propagation through dependency
        
        Args:
            source_service: Service making call
            target_service: Service being called
            
        Returns:
            Error propagation analysis
        """
        stats = self.compute_call_statistics(source_service, target_service)
        
        # Get downstream services
        downstream = self.get_downstream_services(target_service)
        
        # Estimate error impact on downstream
        downstream_impact = []
        for down_service in downstream:
            down_stats = self.compute_call_statistics(target_service, down_service)
            downstream_impact.append({
                'service': down_service,
                'error_rate': down_stats['error_rate'],
                'failures': down_stats['failure_count']
            })
        
        return {
            'source': source_service,
            'target': target_service,
            'direct_error_rate': stats['error_rate'],
            'direct_failures': stats['failure_count'],
            'downstream_services': downstream,
            'downstream_impact': downstream_impact,
            'total_potential_failures': sum(imp['failures'] for imp in downstream_impact)
        }
    
    def find_service_chain(
        self,
        start_service: str,
        end_service: str
    ) -> Optional[List[str]]:
        """
        Find dependency chain between services
        
        Args:
            start_service: Starting service
            end_service: Ending service
            
        Returns:
            Path of services or None
        """
        if not self.dependency_graph:
            return None
        
        # Build networkx graph
        G = nx.DiGraph()
        
        for dep in self.dependency_graph.dependencies:
            G.add_edge(dep.source_service, dep.target_service)
        
        # BFS to find path
        try:
            path = nx.shortest_path(G, start_service, end_service)
            return path
        except nx.NetworkXNoPath:
            return None
        except nx.NodeNotFound:
            return None
    
    def extract_from_traces(
        self,
        traces: List[Dict],
        min_call_threshold: float = 0.01
    ) -> DependencyGraph:
        """
        Extract service calls from traces
        
        Args:
            traces: List of trace dictionaries with service span info
            min_call_threshold: Minimum call frequency to include
            
        Returns:
            Built dependency graph
        """
        for trace in traces:
            spans = trace.get('spans', [])
            
            for i, span in enumerate(spans):
                # Infer service call from span
                service_name = span.get('service_name', 'unknown')
                
                # Look for downstream calls (parent-child relationship)
                for j, other_span in enumerate(spans[i+1:], i+1):
                    if other_span.get('parent_id') == span.get('span_id'):
                        other_service = other_span.get('service_name', 'unknown')
                        
                        # Record call
                        duration = other_span.get('duration_ms', 0)
                        success = other_span.get('status') == 'ok'
                        timestamp = datetime.utcfromtimestamp(other_span.get('timestamp', 0))
                        
                        self.record_service_call(
                            service_name,
                            other_service,
                            duration,
                            success,
                            timestamp
                        )
        
        return self.build_dependency_graph()
    
    def get_network_stats(self) -> Dict:
        """
        Get overall network statistics
        
        Returns:
            Network statistics
        """
        if not self.dependency_graph:
            self.build_dependency_graph()
        
        deps = self.dependency_graph.dependencies
        
        if not deps:
            return {
                'total_services': 0,
                'total_dependencies': 0,
                'avg_latency': 0,
                'avg_error_rate': 0
            }
        
        all_services = set()
        for dep in deps:
            all_services.add(dep.source_service)
            all_services.add(dep.target_service)
        
        return {
            'total_services': len(all_services),
            'total_dependencies': len(deps),
            'avg_latency': sum(d.avg_latency_ms for d in deps) / len(deps),
            'avg_error_rate': sum(d.error_rate for d in deps) / len(deps),
            'total_calls': sum(d.call_volume for d in deps),
            'services': sorted(all_services)
        }
