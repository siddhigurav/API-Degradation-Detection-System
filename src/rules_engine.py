"""
Custom Alert Rules Engine

Allows dynamic creation and evaluation of alert rules with:
- DSL for rule definition
- Template-based rules
- Runtime evaluation
- Testing and validation
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import logging

log = logging.getLogger(__name__)


class RuleType(str, Enum):
    """Rule evaluation type"""
    THRESHOLD = "threshold"
    PERCENTAGE_CHANGE = "percentage_change"
    RATE_OF_CHANGE = "rate_of_change"
    EXPRESSION = "expression"
    COMPOSITE = "composite"


class RuleOperator(str, Enum):
    """Comparison operators"""
    EQUAL = "=="
    NOT_EQUAL = "!="
    GREATER = ">"
    LESS = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    IN = "in"
    CONTAINS = "contains"


class RuleAction(str, Enum):
    """Action on rule trigger"""
    ALERT = "alert"
    NOTIFY = "notify"
    AUTO_REMEDIATE = "auto_remediate"
    ESCALATE = "escalate"
    LOG = "log"


class RuleStatus(str, Enum):
    """Rule status"""
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class AlertRule:
    """Alert rule definition"""
    
    def __init__(
        self,
        rule_id: str,
        name: str,
        description: str,
        rule_type: RuleType
    ):
        self.rule_id = rule_id
        self.name = name
        self.description = description
        self.rule_type = rule_type
        self.status = RuleStatus.DRAFT
        self.enabled = True
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        
        # Rule configuration
        self.condition: Dict = {}
        self.actions: List[RuleAction] = []
        self.severity = "warning"
        self.priority = 5
        
        # Notification
        self.notify_channels: List[str] = []
        self.notify_teams: List[str] = []
        self.notify_escalation_after: int = 300  # seconds
        
        # Testing
        self.test_results: List[Dict] = []
        self.evaluation_count = 0
        self.success_count = 0
        self.failure_count = 0
        
        # Auto-remediation
        self.remediation_template: Optional[str] = None
        self.remediation_dry_run_first = True
    
    def add_condition(self, key: str, operator: RuleOperator, value: Any):
        """Add rule condition"""
        self.condition[key] = {
            "operator": operator.value,
            "value": value
        }
    
    def add_action(self, action: RuleAction, config: Dict = None):
        """Add rule action"""
        self.actions.append({
            "action": action.value,
            "config": config or {}
        })
    
    def add_notification(self, channel: str, teams: List[str] = None):
        """Add notification configuration"""
        self.notify_channels.append(channel)
        if teams:
            self.notify_teams.extend(teams)
    
    def set_auto_remediation(self, template_id: str, dry_run_first: bool = True):
        """Set auto-remediation configuration"""
        self.remediation_template = template_id
        self.remediation_dry_run_first = dry_run_first
    
    def activate(self):
        """Activate the rule"""
        self.status = RuleStatus.ACTIVE
        self.enabled = True
        self.updated_at = datetime.utcnow()
    
    def deactivate(self):
        """Deactivate the rule"""
        self.status = RuleStatus.INACTIVE
        self.enabled = False
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "rule_type": self.rule_type.value,
            "status": self.status.value,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "condition": self.condition,
            "severity": self.severity,
            "priority": self.priority,
            "notify_channels": self.notify_channels,
            "evaluation_count": self.evaluation_count,
            "success_rate": (
                self.success_count / self.evaluation_count
                if self.evaluation_count > 0 else 0.0
            ),
            "remediation_template": self.remediation_template
        }


class RuleEvaluator:
    """Evaluate rules against data"""
    
    @staticmethod
    def evaluate_threshold(
        value: float,
        operator: str,
        threshold: float
    ) -> bool:
        """Evaluate threshold rule"""
        
        if operator == "==":
            return value == threshold
        elif operator == "!=":
            return value != threshold
        elif operator == ">":
            return value > threshold
        elif operator == "<":
            return value < threshold
        elif operator == ">=":
            return value >= threshold
        elif operator == "<=":
            return value <= threshold
        
        return False
    
    @staticmethod
    def evaluate_percentage_change(
        current: float,
        previous: float,
        threshold: float,
        operator: str
    ) -> bool:
        """Evaluate percentage change rule"""
        
        if previous == 0:
            return False
        
        change_percent = abs((current - previous) / previous) * 100
        
        if operator == ">":
            return change_percent > threshold
        elif operator == "<":
            return change_percent < threshold
        elif operator == ">=":
            return change_percent >= threshold
        elif operator == "<=":
            return change_percent <= threshold
        
        return False
    
    @staticmethod
    def evaluate_rate_of_change(
        values: List[float],
        threshold: float,
        operator: str
    ) -> bool:
        """Evaluate rate of change rule"""
        
        if len(values) < 2:
            return False
        
        # Calculate slope
        sum_xy = sum(
            (i + 1) * values[i]
            for i in range(len(values))
        )
        sum_x = sum(i + 1 for i in range(len(values)))
        sum_y = sum(values)
        sum_x2 = sum((i + 1) ** 2 for i in range(len(values)))
        
        n = len(values)
        slope = (
            (n * sum_xy - sum_x * sum_y) /
            (n * sum_x2 - sum_x ** 2)
        )
        
        if operator == ">":
            return slope > threshold
        elif operator == "<":
            return slope < threshold
        
        return False
    
    @staticmethod
    def evaluate_expression(
        expression: str,
        variables: Dict[str, float]
    ) -> bool:
        """Evaluate custom expression"""
        
        try:
            # Sanitize and evaluate
            # Only allow safe operations
            allowed_names = {
                "__builtins__": {},
                "abs": abs,
                "max": max,
                "min": min,
                "sum": sum,
                **variables
            }
            
            return bool(eval(expression, allowed_names))
        except Exception as e:
            log.error(f"Expression evaluation failed: {e}")
            return False


class RuleEngine:
    """Rule management and evaluation"""
    
    def __init__(self):
        """Initialize rule engine"""
        self.rules: Dict[str, AlertRule] = {}
        self.rule_groups: Dict[str, List[str]] = {}
        self.evaluation_history: List[Dict] = []
        self._init_default_rules()
    
    def _init_default_rules(self):
        """Initialize common alert rules"""
        
        # Rule 1: High CPU
        cpu_rule = AlertRule(
            rule_id="rule_cpu_high",
            name="CPU Usage High",
            description="Alert when CPU exceeds 85%",
            rule_type=RuleType.THRESHOLD
        )
        cpu_rule.add_condition("cpu_percent", RuleOperator.GREATER, 85)
        cpu_rule.add_action(RuleAction.ALERT)
        cpu_rule.add_action(RuleAction.NOTIFY)
        cpu_rule.add_notification("slack", teams=["platform"])
        cpu_rule.severity = "warning"
        cpu_rule.activate()
        
        self.register_rule(cpu_rule)
        
        # Rule 2: High Memory
        memory_rule = AlertRule(
            rule_id="rule_memory_high",
            name="Memory Usage High",
            description="Alert when memory exceeds 90%",
            rule_type=RuleType.THRESHOLD
        )
        memory_rule.add_condition("memory_percent", RuleOperator.GREATER, 90)
        memory_rule.add_action(RuleAction.ALERT)
        memory_rule.add_notification("slack", teams=["platform", "ops"])
        memory_rule.add_notification("email", teams=["oncall"])
        memory_rule.severity = "critical"
        memory_rule.activate()
        
        self.register_rule(memory_rule)
        
        # Rule 3: Response Time
        latency_rule = AlertRule(
            rule_id="rule_latency_high",
            name="API Latency High",
            description="Alert when p95 latency > 1000ms",
            rule_type=RuleType.THRESHOLD
        )
        latency_rule.add_condition("latency_p95_ms", RuleOperator.GREATER, 1000)
        latency_rule.add_action(RuleAction.ALERT)
        latency_rule.add_action(RuleAction.AUTO_REMEDIATE)
        latency_rule.add_notification("slack")
        latency_rule.set_auto_remediation("scale_service", dry_run_first=True)
        latency_rule.severity = "warning"
        latency_rule.activate()
        
        self.register_rule(latency_rule)
        
        # Rule 4: Error Rate
        error_rule = AlertRule(
            rule_id="rule_error_rate_high",
            name="Error Rate High",
            description="Alert when error rate > 1%",
            rule_type=RuleType.THRESHOLD
        )
        error_rule.add_condition("error_rate_percent", RuleOperator.GREATER, 1)
        error_rule.add_action(RuleAction.ALERT)
        error_rule.add_action(RuleAction.ESCALATE)
        error_rule.add_notification("slack")
        error_rule.notify_escalation_after = 600
        error_rule.severity = "critical"
        error_rule.activate()
        
        self.register_rule(error_rule)
        
        # Rule 5: Database Connection Pool
        db_conn_rule = AlertRule(
            rule_id="rule_db_conn_exhausted",
            name="DB Connection Pool Exhausted",
            description="Alert when connection pool usage > 95%",
            rule_type=RuleType.THRESHOLD
        )
        db_conn_rule.add_condition("db_pool_usage_percent", RuleOperator.GREATER, 95)
        db_conn_rule.add_action(RuleAction.ALERT)
        db_conn_rule.add_action(RuleAction.AUTO_REMEDIATE)
        db_conn_rule.add_notification("slack", teams=["platform", "dba"])
        db_conn_rule.set_auto_remediation("db_conn_exhausted", dry_run_first=True)
        db_conn_rule.severity = "critical"
        db_conn_rule.activate()
        
        self.register_rule(db_conn_rule)
    
    def register_rule(self, rule: AlertRule):
        """Register alert rule"""
        self.rules[rule.rule_id] = rule
        log.info(f"Registered rule: {rule.rule_id}")
    
    def create_rule(
        self,
        name: str,
        description: str,
        rule_type: RuleType,
        condition: Dict,
        actions: List[RuleAction],
        severity: str = "warning"
    ) -> AlertRule:
        """Create new alert rule"""
        
        rule_id = f"rule_{name.lower().replace(' ', '_')}"
        rule = AlertRule(rule_id, name, description, rule_type)
        rule.severity = severity
        
        for key, cond in condition.items():
            rule.add_condition(
                key,
                RuleOperator(cond["operator"]),
                cond["value"]
            )
        
        for action in actions:
            rule.add_action(action)
        
        self.register_rule(rule)
        return rule
    
    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get rule by ID"""
        return self.rules.get(rule_id)
    
    def get_active_rules(self) -> List[AlertRule]:
        """Get all active rules"""
        return [
            rule for rule in self.rules.values()
            if rule.enabled and rule.status == RuleStatus.ACTIVE
        ]
    
    async def evaluate_rule(
        self,
        rule_id: str,
        data: Dict[str, Any]
    ) -> Tuple[bool, Dict]:
        """Evaluate rule against data"""
        
        rule = self.get_rule(rule_id)
        if not rule or not rule.enabled:
            return False, {}
        
        rule.evaluation_count += 1
        
        try:
            triggered = False
            
            if rule.rule_type == RuleType.THRESHOLD:
                # Evaluate all conditions (AND logic)
                triggered = True
                for key, condition in rule.condition.items():
                    if key not in data:
                        triggered = False
                        break
                    
                    value = data[key]
                    operator = condition["operator"]
                    threshold = condition["value"]
                    
                    if not RuleEvaluator.evaluate_threshold(value, operator, threshold):
                        triggered = False
                        break
            
            elif rule.rule_type == RuleType.PERCENTAGE_CHANGE:
                # Evaluate percentage change
                current = data.get("current_value", 0)
                previous = data.get("previous_value", 0)
                condition = rule.condition.get("change", {})
                
                triggered = RuleEvaluator.evaluate_percentage_change(
                    current,
                    previous,
                    condition.get("value", 0),
                    condition.get("operator", ">")
                )
            
            elif rule.rule_type == RuleType.EXPRESSION:
                # Evaluate custom expression
                expression = rule.condition.get("expression", "")
                triggered = RuleEvaluator.evaluate_expression(expression, data)
            
            if triggered:
                rule.success_count += 1
            else:
                rule.failure_count += 1
            
            # Record evaluation
            self.evaluation_history.append({
                "rule_id": rule_id,
                "triggered": triggered,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            })
            
            return triggered, rule.to_dict()
        
        except Exception as e:
            log.error(f"Rule evaluation failed: {rule_id} - {e}")
            rule.failure_count += 1
            return False, {}
    
    async def test_rule(
        self,
        rule_id: str,
        test_data: List[Dict],
        expected_triggers: List[bool]
    ) -> Dict:
        """Test rule against data"""
        
        rule = self.get_rule(rule_id)
        if not rule:
            return {"error": "Rule not found"}
        
        results = {
            "rule_id": rule_id,
            "total_tests": len(test_data),
            "passed": 0,
            "failed": 0,
            "details": []
        }
        
        for i, (data, expected) in enumerate(zip(test_data, expected_triggers)):
            triggered, _ = await self.evaluate_rule(rule_id, data)
            
            passed = triggered == expected
            results["passed"] += 1 if passed else 0
            results["failed"] += 1 if not passed else 0
            
            results["details"].append({
                "test": i + 1,
                "expected": expected,
                "actual": triggered,
                "passed": passed
            })
        
        rule.test_results.append(results)
        
        return results
    
    def get_rule_statistics(self) -> Dict:
        """Get rule engine statistics"""
        
        active_rules = self.get_active_rules()
        
        return {
            "total_rules": len(self.rules),
            "active_rules": len(active_rules),
            "total_evaluations": sum(r.evaluation_count for r in self.rules.values()),
            "total_triggers": sum(r.success_count for r in self.rules.values()),
            "average_trigger_rate": (
                sum(r.success_count for r in self.rules.values()) /
                sum(r.evaluation_count for r in self.rules.values())
                if sum(r.evaluation_count for r in self.rules.values()) > 0 else 0.0
            )
        }


# Global rule engine
rule_engine = RuleEngine()
