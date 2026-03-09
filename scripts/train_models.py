"""
Model Training Pipeline - Phase 1

Trains baseline models on historical data.
- LSTM Autoencoder for temporal patterns
- Baseline statistics computation
- Model persistence to disk

Run: python scripts/train_models.py --data data/historical_metrics.csv --output models/
"""

import os
import json
import pickle
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, Any
import argparse

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
from tensorflow import keras
from tensorflow.keras import layers, Sequential
import structlog

log = structlog.get_logger()


class LSTMAutoencoderModel:
    """LSTM Autoencoder for anomaly detection"""
    
    def __init__(self, input_dim: int, latent_dim: int = 4, sequence_length: int = 10):
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.sequence_length = sequence_length
        self.threshold = 3.0
        self.model = None
        self.scaler = StandardScaler()
    
    def build_model(self):
        """Build LSTM Autoencoder architecture"""
        self.model = Sequential([
            # Encoder
            layers.LSTM(8, activation='relu', input_shape=(self.sequence_length, self.input_dim)),
            layers.RepeatVector(self.sequence_length),
            # Decoder
            layers.LSTM(8, activation='relu', return_sequences=True),
            layers.TimeDistributed(layers.Dense(self.input_dim))
        ])
        
        self.model.compile(optimizer='adam', loss='mse')
        log.info("lstm_model_built", input_dim=self.input_dim, latent_dim=self.latent_dim)
    
    def _create_sequences(self, data: np.ndarray) -> np.ndarray:
        """Create sequences for LSTM"""
        sequences = []
        for i in range(len(data) - self.sequence_length + 1):
            sequences.append(data[i:i + self.sequence_length])
        return np.array(sequences)
    
    def train(self, data: np.ndarray, epochs: int = 50, batch_size: int = 32):
        """Train LSTM Autoencoder"""
        if self.model is None:
            self.build_model()
        
        # Normalize data
        data_scaled = self.scaler.fit_transform(data)
        
        # Create sequences
        sequences = self._create_sequences(data_scaled)
        
        # Train: reconstruct input
        self.model.fit(
            sequences,
            sequences,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=0.2,
            verbose=0
        )
        
        log.info("lstm_model_trained", sequences=len(sequences), epochs=epochs)
    
    def get_reconstruction_error(self, data_point: np.ndarray) -> float:
        """Compute reconstruction error"""
        if self.model is None:
            raise RuntimeError("Model not trained")
        
        # Normalize
        data_scaled = self.scaler.transform(data_point.reshape(1, -1))
        
        # Reconstruct
        reconstructed = self.model.predict(data_scaled.reshape(1, 1, self.input_dim), verbose=0)
        
        # MSE
        mse = np.mean((data_scaled - reconstructed) ** 2)
        return float(mse)
    
    def save(self, path: str):
        """Save model and scaler"""
        os.makedirs(path, exist_ok=True)
        
        self.model.save(os.path.join(path, 'lstm_model.h5'))
        with open(os.path.join(path, 'lstm_scaler.pkl'), 'wb') as f:
            pickle.dump(self.scaler, f)
        
        log.info("lstm_model_saved", path=path)
    
    def load(self, path: str):
        """Load model and scaler"""
        self.model = keras.models.load_model(os.path.join(path, 'lstm_model.h5'))
        with open(os.path.join(path, 'lstm_scaler.pkl'), 'rb') as f:
            self.scaler = pickle.load(f)
        
        log.info("lstm_model_loaded", path=path)


class IsolationForestModel:
    """Isolation Forest for simple anomaly detection"""
    
    def __init__(self, contamination: float = 0.05):
        self.contamination = contamination
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        self.scaler = StandardScaler()
    
    def train(self, data: np.ndarray):
        """Train Isolation Forest"""
        data_scaled = self.scaler.fit_transform(data)
        self.model.fit(data_scaled)
        
        log.info("isolation_forest_trained", samples=len(data), contamination=self.contamination)
    
    def predict(self, data: np.ndarray) -> Tuple[bool, float]:
        """Predict anomaly"""
        data_scaled = self.scaler.transform(data.reshape(1, -1))
        
        # -1 for anomaly, 1 for normal
        prediction = self.model.predict(data_scaled)[0]
        
        # Get anomaly score (negative for anomalies)
        score = self.model.score_samples(data_scaled)[0]
        
        is_anomaly = prediction == -1
        confidence = min(abs(score) / 2, 1.0)  # Normalize to [0, 1]
        
        return is_anomaly, confidence
    
    def save(self, path: str):
        """Save model"""
        os.makedirs(path, exist_ok=True)
        
        with open(os.path.join(path, 'if_model.pkl'), 'wb') as f:
            pickle.dump(self.model, f)
        with open(os.path.join(path, 'if_scaler.pkl'), 'wb') as f:
            pickle.dump(self.scaler, f)
        
        log.info("isolation_forest_saved", path=path)


class BaselineStatisticsComputer:
    """Compute baseline statistics for each metric"""
    
    def __init__(self):
        self.baselines: Dict[str, Dict[str, Any]] = {}
    
    def compute_baselines(self, df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """
        Compute baselines from historical data
        
        Expected columns: endpoint, metric_name, value
        """
        baselines = {}
        
        for (endpoint, metric_name), group in df.groupby(['endpoint', 'metric_name']):
            values = group['value'].values
            
            baselines[f"{endpoint}:{metric_name}"] = {
                'endpoint': endpoint,
                'metric_name': metric_name,
                'mean': float(np.mean(values)),
                'stddev': float(np.std(values)),
                'p50': float(np.percentile(values, 50)),
                'p95': float(np.percentile(values, 95)),
                'p99': float(np.percentile(values, 99)),
                'min': float(np.min(values)),
                'max': float(np.max(values)),
                'count': len(values),
                'last_updated': datetime.now().isoformat()
            }
        
        self.baselines = baselines
        log.info("baselines_computed", count=len(baselines))
        return baselines
    
    def save(self, path: str):
        """Save baselines to JSON"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump(self.baselines, f, indent=2)
        
        log.info("baselines_saved", path=path, count=len(self.baselines))


def load_sample_data() -> pd.DataFrame:
    """Load or generate sample historical data"""
    
    # Generate synthetic data for demonstration
    np.random.seed(42)
    
    dates = pd.date_range(start='2026-02-01', end='2026-03-08', freq='1min')
    endpoints = ['/api/checkout', '/api/user', '/api/payment']
    metric_names = ['latency_p95', 'error_rate', 'request_rate']
    
    data = []
    
    for endpoint in endpoints:
        for metric_name in metric_names:
            base_value = {
                'latency_p95': 200,
                'error_rate': 0.01,
                'request_rate': 1000
            }[metric_name]
            
            for i, date in enumerate(dates):
                # Realistic variation with trends
                noise = np.random.normal(0, base_value * 0.1)
                trend = np.sin(i / 1440) * base_value * 0.05  # Daily pattern
                value = base_value + noise + trend
                value = max(0, value)  # Ensure non-negative
                
                data.append({
                    'timestamp': date,
                    'endpoint': endpoint,
                    'metric_name': metric_name,
                    'value': value
                })
    
    df = pd.DataFrame(data)
    log.info("sample_data_generated", rows=len(df), endpoints=len(endpoints), metrics=len(metric_names))
    
    return df


def train_all_models(data: pd.DataFrame, output_dir: str):
    """Train all models"""
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Baseline statistics
    log.info("training_baseline_statistics")
    baseline_computer = BaselineStatisticsComputer()
    baselines = baseline_computer.compute_baselines(data)
    baseline_computer.save(os.path.join(output_dir, 'baselines.json'))
    
    # 2. LSTM Autoencoder
    log.info("training_lstm_autoencoder")
    
    # Prepare data for LSTM
    X = data[['value']].values
    if len(X) > 100:
        lstm_model = LSTMAutoencoderModel(input_dim=1, sequence_length=10)
        lstm_model.train(X, epochs=50, batch_size=32)
        lstm_model.save(os.path.join(output_dir, 'lstm'))
    
    # 3. Isolation Forest
    log.info("training_isolation_forest")
    if len(X) > 10:
        if_model = IsolationForestModel(contamination=0.05)
        if_model.train(X)
        if_model.save(os.path.join(output_dir, 'isolation_forest'))
    
    log.info("all_models_trained", output_dir=output_dir)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Train baseline models')
    parser.add_argument('--data', type=str, help='Input CSV file with metrics')
    parser.add_argument('--output', type=str, default='models/', help='Output directory for models')
    parser.add_argument('--generate-sample', action='store_true', help='Generate sample data')
    
    args = parser.parse_args()
    
    # Load data
    if args.data and os.path.exists(args.data):
        log.info("loading_data", path=args.data)
        data = pd.read_csv(args.data)
    elif args.generate_sample:
        log.info("generating_sample_data")
        data = load_sample_data()
    else:
        log.warning("no_data_provided", generating_sample=True)
        data = load_sample_data()
    
    # Train models
    train_all_models(data, args.output)
    
    print(f"✅ Models trained and saved to {args.output}")


if __name__ == '__main__':
    main()
