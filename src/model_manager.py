"""
ML Model Management & Lifecycle

Manages:
- Model versioning and registry
- Training pipeline
- A/B testing between models
- Model evaluation and metrics
- Automatic retraining
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
import json
import logging

log = logging.getLogger(__name__)


class ModelStatus(str, Enum):
    """Model training/deployment status"""
    TRAINING = "training"
    EVALUATING = "evaluating"
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    DEPRECATED = "deprecated"


class ModelType(str, Enum):
    """ML model type"""
    ISOLATION_FOREST = "isolation_forest"
    ONE_CLASS_SVM = "one_class_svm"
    LSTM = "lstm"
    PROPHET = "prophet"
    ENSEMBLE = "ensemble"


class ABTestConfig:
    """A/B test configuration"""
    
    def __init__(
        self,
        test_id: str,
        model_a_id: str,
        model_b_id: str,
        sample_rate: float = 0.5,
        min_samples: int = 100,
        winning_threshold: float = 0.95
    ):
        self.test_id = test_id
        self.model_a_id = model_a_id
        self.model_b_id = model_b_id
        self.sample_rate = sample_rate  # 50% traffic to each
        self.min_samples = min_samples  # Min requests before declaring winner
        self.winning_threshold = winning_threshold  # Confidence threshold
        self.start_time = datetime.utcnow()
        self.end_time = None
        self.winner = None
        self.metrics_a: Dict = {}
        self.metrics_b: Dict = {}
        self.traffic_a = 0
        self.traffic_b = 0


class ModelMetrics:
    """Model evaluation metrics"""
    
    def __init__(self):
        self.precision = 0.0
        self.recall = 0.0
        self.f1_score = 0.0
        self.accuracy = 0.0
        self.auc_roc = 0.0
        self.false_positive_rate = 0.0
        self.false_negative_rate = 0.0
        self.detection_latency_ms = 0.0
        self.training_time_hours = 0.0
        self.model_size_mb = 0.0
        self.predictions_per_second = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "accuracy": self.accuracy,
            "auc_roc": self.auc_roc,
            "false_positive_rate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
            "detection_latency_ms": self.detection_latency_ms,
            "training_time_hours": self.training_time_hours,
            "model_size_mb": self.model_size_mb,
            "predictions_per_second": self.predictions_per_second
        }


class ModelVersion:
    """ML model version"""
    
    def __init__(
        self,
        model_id: str,
        version: str,
        model_type: ModelType,
        training_data_size: int,
        training_window_days: int = 30
    ):
        self.model_id = model_id
        self.version = version
        self.model_type = model_type
        self.status = ModelStatus.TRAINING
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.deployed_at: Optional[datetime] = None
        
        # Training info
        self.training_data_size = training_data_size
        self.training_window_days = training_window_days
        self.hyperparameters: Dict = {}
        self.metrics = ModelMetrics()
        
        # Performance tracking
        self.predictions_made = 0
        self.average_latency_ms = 0.0
        self.accuracy_on_test_set = 0.0
        
        # Metadata
        self.description = ""
        self.tags: List[str] = []
        self.parent_version: Optional[str] = None
    
    def mark_active(self):
        """Mark model as active"""
        self.status = ModelStatus.ACTIVE
        self.deployed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def mark_inactive(self):
        """Mark model as inactive"""
        self.status = ModelStatus.INACTIVE
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "model_id": self.model_id,
            "version": self.version,
            "model_type": self.model_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "training_data_size": self.training_data_size,
            "training_window_days": self.training_window_days,
            "hyperparameters": self.hyperparameters,
            "metrics": self.metrics.to_dict(),
            "predictions_made": self.predictions_made,
            "average_latency_ms": self.average_latency_ms,
            "accuracy_on_test_set": self.accuracy_on_test_set,
            "description": self.description,
            "tags": self.tags
        }


class TrainingPipeline:
    """ML model training pipeline"""
    
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.pipeline_id = f"pipeline_{model_id}_{datetime.utcnow().timestamp()}"
        self.start_time = datetime.utcnow()
        self.end_time: Optional[datetime] = None
        self.status = "running"
        self.progress = 0  # 0-100
        self.stages: List[Dict] = []
        self.errors: List[str] = []
    
    def add_stage(self, name: str, duration_seconds: float, status: str = "completed"):
        """Add training stage"""
        self.stages.append({
            "name": name,
            "duration_seconds": duration_seconds,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def complete(self, success: bool = True):
        """Mark pipeline complete"""
        self.end_time = datetime.utcnow()
        self.status = "completed" if success else "failed"
        self.progress = 100 if success else self.progress


class ModelRegistry:
    """Model version registry and management"""
    
    def __init__(self):
        """Initialize model registry"""
        self.models: Dict[str, List[ModelVersion]] = {}
        self.active_models: Dict[str, ModelVersion] = {}
        self.ab_tests: Dict[str, ABTestConfig] = {}
        self.training_pipelines: List[TrainingPipeline] = []
        self._init_default_models()
    
    def _init_default_models(self):
        """Initialize with default ensemble models"""
        
        # Ensemble model (active)
        ensemble = ModelVersion(
            model_id="ensemble",
            version="1.0",
            model_type=ModelType.ENSEMBLE,
            training_data_size=100000,
            training_window_days=30
        )
        ensemble.description = "Production ensemble: IF + OCSVM + LSTM + Prophet"
        ensemble.hyperparameters = {
            "isolation_forest": {"contamination": 0.01, "n_estimators": 100},
            "one_class_svm": {"nu": 0.05, "kernel": "rbf"},
            "lstm": {"hidden_units": 64, "dropout": 0.2, "epochs": 50},
            "prophet": {"interval_width": 0.95}
        }
        ensemble.metrics.precision = 0.94
        ensemble.metrics.recall = 0.91
        ensemble.metrics.f1_score = 0.925
        ensemble.metrics.accuracy = 0.95
        ensemble.metrics.auc_roc = 0.97
        ensemble.metrics.detection_latency_ms = 125.5
        ensemble.metrics.predictions_per_second = 2500
        ensemble.mark_active()
        
        self.register_model(ensemble)
        self.active_models["ensemble"] = ensemble
        
        # Isolation Forest model
        if_model = ModelVersion(
            model_id="isolation_forest",
            version="2.1",
            model_type=ModelType.ISOLATION_FOREST,
            training_data_size=100000,
            training_window_days=30,
        )
        if_model.description = "Isolation Forest detector"
        if_model.metrics.f1_score = 0.88
        if_model.metrics.auc_roc = 0.94
        if_model.metrics.detection_latency_ms = 45.2
        if_model.mark_active()
        
        self.register_model(if_model)
        
        # LSTM model
        lstm_model = ModelVersion(
            model_id="lstm",
            version="1.3",
            model_type=ModelType.LSTM,
            training_data_size=100000,
            training_window_days=30
        )
        lstm_model.description = "LSTM sequential anomaly detection"
        lstm_model.metrics.f1_score = 0.92
        lstm_model.metrics.auc_roc = 0.96
        lstm_model.metrics.detection_latency_ms = 78.3
        lstm_model.mark_active()
        
        self.register_model(lstm_model)
    
    def register_model(self, model: ModelVersion):
        """Register model version"""
        if model.model_id not in self.models:
            self.models[model.model_id] = []
        
        self.models[model.model_id].append(model)
        log.info(f"Registered model: {model.model_id}:{model.version}")
    
    def get_model(self, model_id: str, version: str = None) -> Optional[ModelVersion]:
        """Get specific model version"""
        if model_id not in self.models:
            return None
        
        versions = self.models[model_id]
        
        if version is None:
            # Return latest version
            return sorted(versions, key=lambda m: m.created_at, reverse=True)[0]
        
        matching = [m for m in versions if m.version == version]
        return matching[0] if matching else None
    
    def get_active_model(self, model_id: str) -> Optional[ModelVersion]:
        """Get active model for prediction"""
        return self.active_models.get(model_id)
    
    def promote_to_active(self, model_id: str, version: str):
        """Promote model version to active"""
        model = self.get_model(model_id, version)
        if not model:
            raise ValueError(f"Model not found: {model_id}:{version}")
        
        # Deactivate current active
        if model_id in self.active_models:
            self.active_models[model_id].mark_inactive()
        
        # Activate new
        model.mark_active()
        self.active_models[model_id] = model
        
        log.info(f"Promoted {model_id}:{version} to active")
    
    def start_ab_test(
        self,
        model_a_id: str,
        model_b_id: str,
        sample_rate: float = 0.5
    ) -> ABTestConfig:
        """Start A/B test between models"""
        test_config = ABTestConfig(
            test_id=f"ab_test_{datetime.utcnow().timestamp()}",
            model_a_id=model_a_id,
            model_b_id=model_b_id,
            sample_rate=sample_rate
        )
        
        self.ab_tests[test_config.test_id] = test_config
        log.info(f"Started A/B test: {test_config.test_id}")
        
        return test_config
    
    def record_ab_test_result(
        self,
        test_id: str,
        model_id: str,
        metric_name: str,
        value: float
    ):
        """Record A/B test result"""
        test = self.ab_tests.get(test_id)
        if not test:
            return
        
        if model_id == test.model_a_id:
            test.metrics_a[metric_name] = value
            test.traffic_a += 1
        elif model_id == test.model_b_id:
            test.metrics_b[metric_name] = value
            test.traffic_b += 1
    
    def evaluate_ab_test(self, test_id: str) -> Optional[str]:
        """Evaluate A/B test and declare winner"""
        test = self.ab_tests.get(test_id)
        if not test:
            return None
        
        total_traffic = test.traffic_a + test.traffic_b
        if total_traffic < test.min_samples:
            log.info(f"A/B test {test_id}: insufficient samples ({total_traffic})")
            return None
        
        # Compare F1 scores
        f1_a = test.metrics_a.get("f1_score", 0)
        f1_b = test.metrics_b.get("f1_score", 0)
        
        if f1_a > f1_b * test.winning_threshold:
            test.winner = test.model_a_id
            log.info(f"A/B test {test_id}: Model A ({test.model_a_id}) wins")
        elif f1_b > f1_a * test.winning_threshold:
            test.winner = test.model_b_id
            log.info(f"A/B test {test_id}: Model B ({test.model_b_id}) wins")
        else:
            log.info(f"A/B test {test_id}: Inconclusive")
        
        test.end_time = datetime.utcnow()
        return test.winner
    
    async def trigger_retraining(
        self,
        model_id: str,
        training_data_size: int,
        force: bool = False
    ) -> TrainingPipeline:
        """Trigger model retraining"""
        
        current = self.get_active_model(model_id)
        if current and not force:
            # Check if retraining is needed (e.g., model is old)
            age_days = (datetime.utcnow() - current.created_at).days
            if age_days < 7:  # Retrain if model > 7 days old
                log.info(f"Model {model_id} is recent, skipping retraining")
                return None
        
        pipeline = TrainingPipeline(model_id)
        
        # Simulate training stages
        pipeline.add_stage("data_collection", 120)
        pipeline.add_stage("data_preprocessing", 300)
        pipeline.add_stage("feature_engineering", 600)
        pipeline.add_stage("model_training", 1800)
        pipeline.add_stage("model_evaluation", 600)
        pipeline.add_stage("hyperparameter_tuning", 1200)
        
        self.training_pipelines.append(pipeline)
        
        log.info(f"Started retraining pipeline for {model_id}")
        
        return pipeline
    
    def get_model_comparison(self, models: List[str]) -> Dict:
        """Compare multiple models"""
        comparison = {}
        
        for model_id in models:
            model = self.get_active_model(model_id)
            if model:
                comparison[model_id] = {
                    "version": model.version,
                    "status": model.status.value,
                    "metrics": model.metrics.to_dict(),
                    "deployed_at": model.deployed_at.isoformat() if model.deployed_at else None
                }
        
        return comparison
    
    def get_registry_stats(self) -> Dict:
        """Get registry statistics"""
        return {
            "total_models": len(self.models),
            "active_models": len(self.active_models),
            "ab_tests_running": sum(1 for t in self.ab_tests.values() if t.end_time is None),
            "training_pipelines": len(self.training_pipelines),
            "model_versions": sum(len(v) for v in self.models.values())
        }


# Global model registry
model_registry = ModelRegistry()
