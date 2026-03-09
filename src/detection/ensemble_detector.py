"""
Ensemble Anomaly Detection Service

Implements a voting ensemble of 4 detection models:
1. Isolation Forest - Unsupervised outlier detection
2. LSTM Autoencoder - Temporal pattern learning
3. Prophet - Time-series forecasting
4. One-Class SVM - Support-based anomaly detection

Consumes features from Kafka feature-store topic
Publishes anomalies to Kafka anomalies topic
"""

import json
import pickle
import logging
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict

import structlog
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

try:
    import tensorflow as tf
    from tensorflow import keras
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False

from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from fbprophet import Prophet
import pandas as pd

log = structlog.get_logger()


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class FeatureData:
    """Feature data from feature-store topic"""
    timestamp: datetime
    endpoint: str
    metric_name: str
    values: Dict[str, float]  # window_1m, window_5m, etc.
    baseline_mean: float
    baseline_stddev: float
    
    @classmethod
    def from_kafka_message(cls, msg: dict) -> 'FeatureData':
        """Parse Kafka message"""
        return cls(
            timestamp=datetime.fromisoformat(msg['timestamp']),
            endpoint=msg['endpoint'],
            metric_name=msg['metric_name'],
            values=msg['values'],
            baseline_mean=msg.get('baseline_mean', 0),
            baseline_stddev=msg.get('baseline_stddev', 1)
        )


@dataclass
class ModelPrediction:
    """Single model prediction"""
    model_name: str
    is_anomaly: bool
    confidence: float  # 0-1
    score: float  # Raw anomaly score
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnomalyDetection:
    """Ensemble anomaly detection result"""
    timestamp: datetime
    endpoint: str
    metric_name: str
    is_anomaly: bool
    anomaly_score: float  # 0-1
    ensemble_confidence: float
    model_agreement: int  # 0-4
    predictions: List[ModelPrediction]
    feature_context: Dict[str, float]
    
    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'endpoint': self.endpoint,
            'metric_name': self.metric_name,
            'is_anomaly': self.is_anomaly,
            'anomaly_score': float(self.anomaly_score),
            'ensemble_confidence': float(self.ensemble_confidence),
            'model_agreement': self.model_agreement,
            'predictions': [p.to_dict() for p in self.predictions],
            'feature_context': {k: float(v) for k, v in self.feature_context.items()}
        }


# ============================================================================
# Model Loaders
# ============================================================================

class LSTMAutoencoderModel:
    """LSTM Autoencoder for time-series anomaly detection"""
    
    def __init__(self, model_path: Path):
        self.model_path = model_path
        self.model = None
        self.scaler = StandardScaler()
        self.is_loaded = False
        self.reconstruction_error_threshold = 0.0
        
    def load(self):
        """Load trained model"""
        try:
            if not self.model_path.exists():
                log.warning("LSTM model not found", path=str(self.model_path))
                return False
            
            # Load Keras model
            self.model = keras.models.load_model(str(self.model_path / 'model.h5'))
            
            # Load scaler
            scaler_path = self.model_path / 'scaler.pkl'
            if scaler_path.exists():
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
            
            # Load threshold (computed during training)
            threshold_path = self.model_path / 'threshold.json'
            if threshold_path.exists():
                with open(threshold_path, 'r') as f:
                    data = json.load(f)
                    self.reconstruction_error_threshold = data.get('threshold', 2.0)
            
            self.is_loaded = True
            log.info("LSTM model loaded", threshold=self.reconstruction_error_threshold)
            return True
        except Exception as e:
            log.error("Failed to load LSTM model", error=str(e))
            return False
    
    def predict(self, features: np.ndarray) -> Tuple[bool, float, float]:
        """
        Predict anomaly
        
        Args:
            features: (sequence_length, num_features) array
            
        Returns:
            (is_anomaly, confidence, score)
        """
        if not self.is_loaded or self.model is None:
            return False, 0.0, 0.0
        
        try:
            # Scale features
            scaled = self.scaler.transform(features)
            
            # Get reconstruction error
            reconstructed = self.model.predict(scaled[np.newaxis, :], verbose=0)
            error = np.mean(np.abs(scaled - reconstructed[0]))
            
            # Compute anomaly score (0-1)
            # Assume threshold is typically 2-3x std from normal reconstruction error
            normalized_error = min(error / (self.reconstruction_error_threshold + 1e-6), 1.0)
            
            # Determine if anomaly
            is_anomaly = error > self.reconstruction_error_threshold
            confidence = normalized_error
            
            return is_anomaly, confidence, float(error)
        except Exception as e:
            log.error("LSTM prediction failed", error=str(e))
            return False, 0.0, 0.0


class IsolationForestModel:
    """Isolation Forest for anomaly detection"""
    
    def __init__(self, model_path: Path):
        self.model_path = model_path
        self.model = None
        self.scaler = StandardScaler()
        self.is_loaded = False
        self.feature_names = []
        
    def load(self):
        """Load trained model"""
        try:
            if not self.model_path.exists():
                log.warning("Isolation Forest model not found", path=str(self.model_path))
                return False
            
            model_file = self.model_path / 'model.pkl'
            if not model_file.exists():
                log.warning("Isolation Forest pkl not found")
                return False
            
            with open(model_file, 'rb') as f:
                self.model = pickle.load(f)
            
            # Load scaler
            scaler_path = self.model_path / 'scaler.pkl'
            if scaler_path.exists():
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
            
            # Load feature names
            features_path = self.model_path / 'features.json'
            if features_path.exists():
                with open(features_path, 'r') as f:
                    data = json.load(f)
                    self.feature_names = data.get('features', [])
            
            self.is_loaded = True
            log.info("Isolation Forest model loaded")
            return True
        except Exception as e:
            log.error("Failed to load Isolation Forest model", error=str(e))
            return False
    
    def predict(self, features: np.ndarray) -> Tuple[bool, float, float]:
        """
        Predict anomaly
        
        Args:
            features: 1D array of feature values
            
        Returns:
            (is_anomaly, confidence, score)
        """
        if not self.is_loaded or self.model is None:
            return False, 0.0, 0.0
        
        try:
            # Scale features
            scaled = self.scaler.transform(features.reshape(1, -1))[0]
            
            # Predict
            prediction = self.model.predict(scaled.reshape(1, -1))[0]  # -1 for anomaly, 1 for normal
            score = self.model.score_samples(scaled.reshape(1, -1))[0]  # Anomaly score
            
            is_anomaly = prediction == -1
            # Normalize score to 0-1 (lower score = more anomalous)
            confidence = max(0, min(1, 1 - (score + 0.5)))  # Heuristic normalization
            
            return is_anomaly, confidence, float(score)
        except Exception as e:
            log.error("Isolation Forest prediction failed", error=str(e))
            return False, 0.0, 0.0


class OneClassSVMModel:
    """One-Class SVM for anomaly detection"""
    
    def __init__(self, model_path: Path):
        self.model_path = model_path
        self.model = None
        self.scaler = StandardScaler()
        self.is_loaded = False
        
    def load(self):
        """Load trained model"""
        try:
            if not self.model_path.exists():
                log.warning("One-Class SVM model not found", path=str(self.model_path))
                return False
            
            model_file = self.model_path / 'model.pkl'
            if not model_file.exists():
                log.warning("One-Class SVM pkl not found")
                return False
            
            with open(model_file, 'rb') as f:
                self.model = pickle.load(f)
            
            # Load scaler
            scaler_path = self.model_path / 'scaler.pkl'
            if scaler_path.exists():
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
            
            self.is_loaded = True
            log.info("One-Class SVM model loaded")
            return True
        except Exception as e:
            log.error("Failed to load One-Class SVM model", error=str(e))
            return False
    
    def predict(self, features: np.ndarray) -> Tuple[bool, float, float]:
        """
        Predict anomaly
        
        Args:
            features: 1D array of feature values
            
        Returns:
            (is_anomaly, confidence, score)
        """
        if not self.is_loaded or self.model is None:
            return False, 0.0, 0.0
        
        try:
            # Scale features
            scaled = self.scaler.transform(features.reshape(1, -1))[0]
            
            # Predict
            prediction = self.model.predict(scaled.reshape(1, -1))[0]  # -1 for anomaly, 1 for normal
            score = self.model.decision_function(scaled.reshape(1, -1))[0]
            
            is_anomaly = prediction == -1
            # Normalize score to 0-1
            confidence = max(0, min(1, 1 - (score / 10)))  # Heuristic normalization
            
            return is_anomaly, confidence, float(score)
        except Exception as e:
            log.error("One-Class SVM prediction failed", error=str(e))
            return False, 0.0, 0.0


# ============================================================================
# Ensemble Detector
# ============================================================================

class EnsembleDetector:
    """Anomaly detection ensemble"""
    
    def __init__(self, models_dir: Path, min_agreement: int = 2):
        """
        Initialize ensemble
        
        Args:
            models_dir: Directory containing trained models
            min_agreement: Minimum model votes for anomaly consensus
        """
        self.models_dir = Path(models_dir)
        self.min_agreement = min_agreement
        
        # Initialize model loaders
        self.models = {
            'isolation_forest': IsolationForestModel(self.models_dir / 'isolation_forest'),
            'one_class_svm': OneClassSVMModel(self.models_dir / 'one_class_svm'),
        }
        
        # Optional LSTM (requires TensorFlow)
        if TENSORFLOW_AVAILABLE:
            self.models['lstm'] = LSTMAutoencoderModel(self.models_dir / 'lstm')
        
        self.is_ready = False
        self.prediction_count = 0
        self.feature_history = defaultdict(list)  # For Prophet training
        
    def load_models(self) -> bool:
        """Load all available models"""
        try:
            loaded_count = 0
            for name, model in self.models.items():
                if model.load():
                    loaded_count += 1
                    log.info("Model loaded", model=name)
            
            self.is_ready = loaded_count >= 2  # Need at least 2 models
            log.info("Ensemble ready", is_ready=self.is_ready, loaded_models=loaded_count)
            return self.is_ready
        except Exception as e:
            log.error("Failed to load models", error=str(e))
            return False
    
    def detect(self, feature_data: FeatureData) -> Optional[AnomalyDetection]:
        """
        Detect anomaly in feature data
        
        Args:
            feature_data: Feature data from Kafka
            
        Returns:
            AnomalyDetection result or None if unable to predict
        """
        if not self.is_ready:
            log.warning("Ensemble not ready")
            return None
        
        try:
            # Prepare feature vector
            feature_values = list(feature_data.values.values())
            feature_array = np.array(feature_values, dtype=np.float32)
            
            # Skip if all zeros
            if np.allclose(feature_array, 0):
                return None
            
            # Get predictions from all models
            predictions: List[ModelPrediction] = []
            anomaly_votes = 0
            total_confidence = 0.0
            
            # Isolation Forest
            is_anom, conf, score = self.models['isolation_forest'].predict(feature_array)
            predictions.append(ModelPrediction(
                model_name='isolation_forest',
                is_anomaly=is_anom,
                confidence=conf,
                score=score
            ))
            if is_anom:
                anomaly_votes += 1
            total_confidence += conf
            
            # One-Class SVM
            is_anom, conf, score = self.models['one_class_svm'].predict(feature_array)
            predictions.append(ModelPrediction(
                model_name='one_class_svm',
                is_anomaly=is_anom,
                confidence=conf,
                score=score
            ))
            if is_anom:
                anomaly_votes += 1
            total_confidence += conf
            
            # LSTM (if available)
            if 'lstm' in self.models and self.models['lstm'].is_loaded:
                # LSTM needs (sequence_length, features) - pad if needed
                if len(feature_array) < 10:
                    padded = np.zeros((10,))
                    padded[:len(feature_array)] = feature_array
                else:
                    padded = feature_array[:10]
                
                is_anom, conf, score = self.models['lstm'].predict(padded)
                predictions.append(ModelPrediction(
                    model_name='lstm',
                    is_anomaly=is_anom,
                    confidence=conf,
                    score=score
                ))
                if is_anom:
                    anomaly_votes += 1
                total_confidence += conf
            
            # Ensemble decision
            num_predictions = len(predictions)
            avg_confidence = total_confidence / num_predictions if num_predictions > 0 else 0.0
            is_anomaly_ensemble = anomaly_votes >= self.min_agreement
            
            result = AnomalyDetection(
                timestamp=feature_data.timestamp,
                endpoint=feature_data.endpoint,
                metric_name=feature_data.metric_name,
                is_anomaly=is_anomaly_ensemble,
                anomaly_score=min(anomaly_votes / num_predictions, 1.0),
                ensemble_confidence=avg_confidence,
                model_agreement=anomaly_votes,
                predictions=predictions,
                feature_context={
                    'baseline_mean': feature_data.baseline_mean,
                    'baseline_stddev': feature_data.baseline_stddev,
                    'z_score': (feature_data.values.get('value', 0) - feature_data.baseline_mean) / (feature_data.baseline_stddev + 1e-6)
                }
            )
            
            self.prediction_count += 1
            return result
            
        except Exception as e:
            log.error("Detection failed", error=str(e), endpoint=feature_data.endpoint)
            return None


# ============================================================================
# Streaming Service
# ============================================================================

class EnsembleDetectionService:
    """Kafka-based anomaly detection service"""
    
    def __init__(self, config):
        self.config = config
        self.detector = EnsembleDetector(
            models_dir=Path(config.MODELS_DIR),
            min_agreement=config.MODELS_ENSEMBLE_MIN_AGREEMENT
        )
        
        # Kafka setup
        self.consumer = None
        self.producer = None
        self.running = False
        
    def setup(self) -> bool:
        """Initialize Kafka connections and load models"""
        try:
            # Load models
            if not self.detector.load_models():
                log.error("Failed to load detection models")
                return False
            
            # Setup Kafka consumer
            bootstrap_servers = self.config.KAFKA_BOOTSTRAP_SERVERS.split(',')
            self.consumer = KafkaConsumer(
                self.config.KAFKA_TOPICS['features'],
                bootstrap_servers=bootstrap_servers,
                group_id='ensemble_detector',
                auto_offset_reset='latest',
                consumer_timeout_ms=1000,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            
            # Setup Kafka producer
            self.producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
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
        log.info("Starting anomaly detection service")
        
        try:
            while self.running:
                try:
                    for message in self.consumer:
                        if not self.running:
                            break
                        
                        try:
                            # Parse feature data
                            feature_data = FeatureData.from_kafka_message(message.value)
                            
                            # Detect anomalies
                            result = self.detector.detect(feature_data)
                            
                            if result:
                                # Publish to anomalies topic
                                self.producer.send(
                                    self.config.KAFKA_TOPICS['anomalies'],
                                    value=result.to_dict()
                                )
                                
                                if result.is_anomaly:
                                    log.info(
                                        "Anomaly detected",
                                        endpoint=result.endpoint,
                                        metric=result.metric_name,
                                        score=result.anomaly_score,
                                        agreement=result.model_agreement
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
        log.info("Service stopped", predictions=self.detector.prediction_count)


def main():
    """Main entry point"""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    
    from src.config import settings
    
    # Configure structured logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    service = EnsembleDetectionService(settings)
    service.run()


if __name__ == '__main__':
    main()
