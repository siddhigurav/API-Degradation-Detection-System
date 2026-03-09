"""
Causal Inference Analyzer

Uses DoWhy library to discover causal relationships
between metrics and analyze root causes.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
import structlog

try:
    from dowhy import CausalModel
except ImportError:
    CausalModel = None

from src.rca.models import (
    CausalRelationship, CausalGraph, RCAFinding, CausalityConfidence
)

log = structlog.get_logger()


class CausalAnalyzer:
    """Performs causal inference on metrics"""
    
    def __init__(self):
        """Initialize causal analyzer"""
        if CausalModel is None:
            log.warning("DoWhy not installed - causal analysis unavailable")
        
        self.causal_cache: Dict[Tuple[str, str], CausalRelationship] = {}
        self.discovered_edges: Set[Tuple[str, str]] = set()
        
    def estimate_treatment_effect(
        self,
        treatment_metric: str,
        outcome_metric: str,
        confounder_metrics: List[str],
        df: pd.DataFrame
    ) -> Tuple[float, float]:
        """
        Estimate causal effect of treatment on outcome
        
        Args:
            treatment_metric: Potential cause metric
            outcome_metric: Potential effect metric
            confounder_metrics: Potential confounders to adjust for
            df: DataFrame with metric values
            
        Returns:
            (treatment_effect, confidence_score)
        """
        if CausalModel is None:
            log.warning("DoWhy not available - returning 0 effect")
            return 0.0, 0.0
        
        # Validate data
        if treatment_metric not in df.columns or outcome_metric not in df.columns:
            return 0.0, 0.0
        
        if len(df) < 20:  # Need min samples
            return 0.0, 0.0
        
        # Build causal graph with confounders
        # Simple DAG: confounders -> treatment, confounders -> outcome, treatment -> outcome
        graph_edges = []
        
        # Confounder edges
        for confounder in confounder_metrics:
            if confounder in df.columns:
                graph_edges.append([confounder, treatment_metric])
                graph_edges.append([confounder, outcome_metric])
        
        # Treatment to outcome
        graph_edges.append([treatment_metric, outcome_metric])
        
        if not graph_edges:
            graph_edges = [[treatment_metric, outcome_metric]]
        
        # Convert to gml format for DoWhy
        gml_graph = self._edges_to_gml(graph_edges)
        
        try:
            # Create causal model
            model = CausalModel(
                data=df,
                treatment=treatment_metric,
                outcome=outcome_metric,
                common_causes=confounder_metrics,
                instruments=[],
                graph=gml_graph
            )
            
            # Estimate effect using multiple methods
            # Method 1: Backdoor adjustment
            identified_estimand = model.identify_effect(
                proceed_when_unidentifiable=True
            )
            
            estimate = model.estimate_effect(
                identified_estimand,
                method_name="backdoor.linear_regression"
            )
            
            treatment_effect = float(estimate.value) if estimate.value else 0.0
            
            # Calculate confidence
            # Based on sample size and variance
            confidence = min(1.0, len(df) / 100.0)
            
            return treatment_effect, confidence
            
        except Exception as e:
            log.warning("Causal estimation failed", error=str(e))
            return 0.0, 0.0
    
    def _edges_to_gml(self, edges: List[List[str]]) -> str:
        """
        Convert edge list to GML format
        
        Args:
            edges: List of [source, target] edges
            
        Returns:
            GML format string
        """
        nodes = set()
        for src, tgt in edges:
            nodes.add(src)
            nodes.add(tgt)
        
        gml = "digraph {\n"
        
        # Add nodes
        for i, node in enumerate(nodes):
            gml += f'  "{node}";\n'
        
        # Add edges
        for src, tgt in edges:
            gml += f'  "{src}" -> "{tgt}";\n'
        
        gml += "}"
        
        return gml
    
    def discover_causal_relationships(
        self,
        metrics: List[str],
        df: pd.DataFrame,
        min_confidence: float = 0.3
    ) -> CausalGraph:
        """
        Discover causal relationships between metrics
        
        Args:
            metrics: Metrics to analyze
            df: DataFrame with metric values
            min_confidence: Minimum confidence threshold
            
        Returns:
            CausalGraph with discovered relationships
        """
        relationships = []
        
        # Analyze pairwise relationships
        for i, metric_1 in enumerate(metrics):
            for metric_2 in metrics[i+1:]:
                if metric_1 not in df.columns or metric_2 not in df.columns:
                    continue
                
                # Forward: metric_1 -> metric_2
                effect_1_to_2, conf_1_to_2 = self.estimate_treatment_effect(
                    metric_1, metric_2, 
                    [m for m in metrics if m != metric_1 and m != metric_2],
                    df
                )
                
                # Reverse: metric_2 -> metric_1
                effect_2_to_1, conf_2_to_1 = self.estimate_treatment_effect(
                    metric_2, metric_1,
                    [m for m in metrics if m != metric_1 and m != metric_2],
                    df
                )
                
                # Determine direction based on effect strength
                if abs(effect_1_to_2) > abs(effect_2_to_1) and conf_1_to_2 >= min_confidence:
                    # metric_1 causes metric_2
                    confidence = self._confidence_to_enum(conf_1_to_2)
                    rel = CausalRelationship(
                        cause_metric=metric_1,
                        effect_metric=metric_2,
                        treatment_effect=effect_1_to_2,
                        confidence=confidence,
                        backdoor_adjustment=True,
                        timestamp=datetime.utcnow()
                    )
                    relationships.append(rel)
                    self.discovered_edges.add((metric_1, metric_2))
                    
                elif conf_2_to_1 >= min_confidence:
                    # metric_2 causes metric_1
                    confidence = self._confidence_to_enum(conf_2_to_1)
                    rel = CausalRelationship(
                        cause_metric=metric_2,
                        effect_metric=metric_1,
                        treatment_effect=effect_2_to_1,
                        confidence=confidence,
                        backdoor_adjustment=True,
                        timestamp=datetime.utcnow()
                    )
                    relationships.append(rel)
                    self.discovered_edges.add((metric_2, metric_1))
        
        log.info(
            "Causal discovery complete",
            relationships_found=len(relationships)
        )
        
        return CausalGraph(
            relationships=relationships,
            timestamp=datetime.utcnow()
        )
    
    def _confidence_to_enum(self, confidence_score: float) -> CausalityConfidence:
        """Convert confidence score to enum"""
        if confidence_score >= 0.7:
            return CausalityConfidence.HIGH
        elif confidence_score >= 0.5:
            return CausalityConfidence.MEDIUM
        elif confidence_score >= 0.3:
            return CausalityConfidence.LOW
        else:
            return CausalityConfidence.INSUFFICIENT
    
    def propagate_anomaly(
        self,
        causal_graph: CausalGraph,
        root_metric: str,
        affected_metrics: List[str]
    ) -> Dict[str, RCAFinding]:
        """
        Propagate anomaly through causal graph
        
        Args:
            causal_graph: Discovered causal relationships
            root_metric: Anomalous metric (suspected root)
            affected_metrics: Metrics showing anomalies
            
        Returns:
            Mapping of metric to RCAFinding (root cause, contributing, symptom)
        """
        findings = {}
        
        # Find causality chains from root_metric
        causality_chains = causal_graph.get_causality_chain(root_metric)
        
        # Classify each affected metric
        for metric in affected_metrics:
            if metric == root_metric:
                findings[metric] = RCAFinding.ROOT_CAUSE
            elif any(metric in chain for chain in causality_chains):
                # Check if direct child (contributing) or downstream (symptom)
                # Direct children are contributing factors
                direct_effects = [
                    rel.effect_metric for rel in causal_graph.relationships
                    if rel.cause_metric == root_metric
                ]
                
                if metric in direct_effects:
                    findings[metric] = RCAFinding.CONTRIBUTING_FACTOR
                else:
                    findings[metric] = RCAFinding.SYMPTOM
            else:
                findings[metric] = RCAFinding.UNRELATED
        
        return findings
    
    def estimate_intervention_effect(
        self,
        causal_graph: CausalGraph,
        metric_to_fix: str,
        intervention_amount: float = -1.0
    ) -> Dict[str, float]:
        """
        Estimate impact of intervening on metric
        
        Args:
            causal_graph: Causal graph
            metric_to_fix: Metric to intervene on
            intervention_amount: Amount to change (negative = reduce)
            
        Returns:
            Estimated impact on downstream metrics
        """
        impacts = {}
        
        # Find all downstream metrics
        queue = [metric_to_fix]
        visited = set()
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            # Find direct effects
            for rel in causal_graph.relationships:
                if rel.cause_metric == current:
                    effect_metric = rel.effect_metric
                    
                    # Cumulative effect
                    impact = intervention_amount * rel.treatment_effect
                    
                    if effect_metric in impacts:
                        impacts[effect_metric] += impact
                    else:
                        impacts[effect_metric] = impact
                    
                    queue.append(effect_metric)
        
        return impacts
    
    def validate_causal_assumption(
        self,
        treatment_metric: str,
        outcome_metric: str,
        df: pd.DataFrame
    ) -> Tuple[bool, str]:
        """
        Validate causal assumptions (overlap, no unmeasured confounding)
        
        Args:
            treatment_metric: Treatment variable
            outcome_metric: Outcome variable
            df: Data
            
        Returns:
            (is_valid, reason)
        """
        # Check overlap assumption
        # Treatment should have variation across outcome values
        
        if treatment_metric not in df.columns or outcome_metric not in df.columns:
            return False, "Missing required columns"
        
        treatment_var = df[treatment_metric].var()
        outcome_var = df[outcome_metric].var()
        
        if treatment_var < 0.01 or outcome_var < 0.01:
            return False, "Insufficient variance in variables"
        
        # Check sample size
        if len(df) < 30:
            return False, "Insufficient sample size"
        
        # Check for extreme values
        treatment_range = df[treatment_metric].max() - df[treatment_metric].min()
        outcome_range = df[outcome_metric].max() - df[outcome_metric].min()
        
        if treatment_range == 0 or outcome_range == 0:
            return False, "No variance in data"
        
        return True, "Assumptions satisfied"
    
    def explain_causal_path(
        self,
        causal_graph: CausalGraph,
        root_cause: str,
        target_symptom: str
    ) -> Optional[List[str]]:
        """
        Find causal path from root cause to symptom
        
        Args:
            causal_graph: Causal graph
            root_cause: Root cause metric
            target_symptom: Target symptom metric
            
        Returns:
            Path through metrics or None if no path
        """
        # BFS to find path
        queue = [(root_cause, [root_cause])]
        visited = {root_cause}
        
        while queue:
            current, path = queue.pop(0)
            
            if current == target_symptom:
                return path
            
            # Find next metrics
            for rel in causal_graph.relationships:
                if rel.cause_metric == current and rel.effect_metric not in visited:
                    visited.add(rel.effect_metric)
                    queue.append((rel.effect_metric, path + [rel.effect_metric]))
        
        return None
