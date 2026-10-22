"""
Gradient Boosting Time-Series Forecaster Plugin.

Trains a GradientBoostingRegressor on-the-fly using historical data
and produces multi-step recursive forecasts. Works for any timeseries
attribute without pre-training.

Feature engineering:
  - Time-based: hour of day, day of week, month (sin/cos encoded)
  - Lag features: t-1, t-2, t-3, t-24 (if enough data)
  - Rolling statistics: mean_6h, std_6h, mean_24h (if enough data)
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone
import math

import numpy as np

from app.plugins.base import IntelligencePlugin

logger = logging.getLogger(__name__)

# Minimum data points required to train the model
MIN_TRAIN_POINTS = 24


class GradientBoostingPredictor(IntelligencePlugin):
    """
    Feature-based time-series forecaster using Gradient Boosting.

    Trains on the provided historical data at inference time.
    Extracts time-based features, lag features, and rolling statistics.
    Produces multi-step recursive forecasts for the prediction horizon.
    """

    @property
    def name(self) -> str:
        return "gradient_boosting_predictor"

    async def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze historical data and generate predictions.

        Expected data format:
        {
            "entity_id": "urn:ngsi-ld:AgriSensor:sensor-123",
            "attribute": "temperature",
            "historical_data": [
                {"timestamp": "2024-01-15T10:00:00Z", "value": 20.5},
                ...
            ],
            "prediction_horizon": 24  # hours
        }

        Returns:
        {
            "predictions": [
                {"timestamp": "...", "value": ...},
                ...
            ],
            "confidence": 0.75,
            "model": "gradient_boosting_predictor",
            "metadata": {...}
        }
        """
        try:
            from sklearn.ensemble import GradientBoostingRegressor
        except ImportError:
            logger.error("scikit-learn not installed.")
            raise ImportError(
                "scikit-learn is required for GradientBoostingPredictor. "
                "Install it with: pip install scikit-learn"
            )

        historical_data = data.get("historical_data", [])
        if len(historical_data) < MIN_TRAIN_POINTS:
            raise ValueError(
                f"Need at least {MIN_TRAIN_POINTS} historical data points, "
                f"got {len(historical_data)}"
            )

        prediction_horizon = data.get("prediction_horizon", 24)

        # ---- 1. Parse historical data into numpy arrays ----
        timestamps, values = self._parse_historical(historical_data)

        # ---- 2. Feature engineering ----
        X, y = self._build_features(timestamps, values)
        if len(X) < 10:
            raise ValueError("Not enough feature rows after lag engineering")

        # ---- 3. Train model ----
        model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            random_state=42,
        )
        model.fit(X, y)

        # ---- 4. Recursive multi-step forecast ----
        last_timestamp = timestamps[-1]
        predictions = self._recursive_forecast(
            model, timestamps, values, last_timestamp, prediction_horizon
        )

        # ---- 5. Confidence estimation ----
        # Use the model's training score (R²) as a proxy for confidence,
        # degraded by forecast horizon distance.
        train_score = max(0.0, model.score(X, y))
        confidence = round(
            max(0.3, train_score * (1.0 - prediction_horizon / 200)), 2
        )

        n_points = len(values)
        return {
            "predictions": predictions,
            "confidence": confidence,
            "model": self.name,
            "metadata": {
                "data_points": n_points,
                "train_score": round(train_score, 4),
                "n_features": X.shape[1],
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_historical(
        historical_data: list,
    ):
        """Parse historical data into (timestamps, values) numpy arrays."""
        timestamps = []
        values_list = []
        for point in historical_data:
            ts_str = point["timestamp"]
            if isinstance(ts_str, str):
                ts_str = ts_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts_str)
            else:
                dt = ts_str
            timestamps.append(dt)
            values_list.append(float(point["value"]))
        return (
            np.array(timestamps, dtype=object),
            np.array(values_list, dtype=np.float64),
        )

    @staticmethod
    def _time_features(dt: datetime) -> List[float]:
        """Extract cyclical time-based features from a datetime."""
        hour = dt.hour + dt.minute / 60.0
        dow = dt.weekday()  # 0=Monday, 6=Sunday
        month = dt.month
        # Sin/cos encoding for cyclical features
        hour_sin = math.sin(2 * math.pi * hour / 24.0)
        hour_cos = math.cos(2 * math.pi * hour / 24.0)
        dow_sin = math.sin(2 * math.pi * dow / 7.0)
        dow_cos = math.cos(2 * math.pi * dow / 7.0)
        month_sin = math.sin(2 * math.pi * month / 12.0)
        month_cos = math.cos(2 * math.pi * month / 12.0)
        return [hour_sin, hour_cos, dow_sin, dow_cos, month_sin, month_cos]

    def _build_features(
        self,
        timestamps: np.ndarray,
        values: np.ndarray,
    ):
        """
        Build feature matrix X and target vector y from historical data.

        Features per row:
          - time_features(timestamp_i): 6 features (sin/cos encoded)
          - lag_1: value at i-1
          - lag_2: value at i-2
          - lag_3: value at i-3
          - lag_24: value at i-24 (if available, else global mean)
          - rolling_mean_6: mean of last 6 values
          - rolling_std_6: std of last 6 values

        Target: value at i
        """
        n = len(values)
        global_mean = float(np.mean(values))
        global_std = float(np.std(values)) if n > 1 else 1.0

        feature_rows = []
        targets = []

        start_idx = max(3, 1)  # Need at least lag_1..lag_3
        for i in range(start_idx, n):
            dt = timestamps[i]
            time_feats = self._time_features(dt)

            lag_1 = values[i - 1]
            lag_2 = values[i - 2] if i >= 2 else global_mean
            lag_3 = values[i - 3] if i >= 3 else global_mean

            # lag_24: approx 24 hours ago (if enough data)
            lag_24 = values[i - 24] if i >= 24 else global_mean

            # Rolling statistics over last 6 points
            window_start = max(0, i - 6)
            window = values[window_start:i]
            rolling_mean_6 = float(np.mean(window)) if len(window) > 0 else global_mean
            rolling_std_6 = float(np.std(window)) if len(window) > 1 else 0.0

            row = time_feats + [
                lag_1,
                lag_2,
                lag_3,
                lag_24,
                rolling_mean_6,
                rolling_std_6,
            ]
            feature_rows.append(row)
            targets.append(float(values[i]))

        return np.array(feature_rows, dtype=np.float64), np.array(targets, dtype=np.float64)

    def _recursive_forecast(
        self,
        model,
        timestamps: np.ndarray,
        values: np.ndarray,
        last_timestamp: datetime,
        horizon: int,
    ) -> List[Dict[str, Any]]:
        """
        Recursive multi-step forecast.

        Predicts step 1, appends to the value history, predicts step 2, etc.
        """
        predictions: List[Dict[str, Any]] = []
        values_list = list(values)
        timestamps_list = list(timestamps)

        current_ts = last_timestamp + timedelta(hours=1)
        for _step in range(horizon):
            n = len(values_list)

            # Build feature vector using the same logic as _build_features
            time_feats = self._time_features(current_ts)

            global_mean = float(np.mean(values_list)) if values_list else 0.0

            lag_1 = values_list[-1] if n >= 1 else global_mean
            lag_2 = values_list[-2] if n >= 2 else global_mean
            lag_3 = values_list[-3] if n >= 3 else global_mean
            lag_24 = values_list[-24] if n >= 24 else global_mean

            window_start = max(0, n - 6)
            window = values_list[window_start:n]
            rolling_mean_6 = float(np.mean(window)) if window else global_mean
            rolling_std_6 = float(np.std(window)) if len(window) > 1 else 0.0

            features_row = time_feats + [
                lag_1,
                lag_2,
                lag_3,
                lag_24,
                rolling_mean_6,
                rolling_std_6,
            ]
            X_pred = np.array([features_row], dtype=np.float64)

            # Predict next value
            predicted_value = float(model.predict(X_pred)[0])

            predictions.append({
                "timestamp": current_ts.isoformat().replace("+00:00", "Z"),
                "value": round(predicted_value, 2),
            })

            # Append to history for next recursive step
            values_list.append(predicted_value)
            timestamps_list.append(current_ts)
            current_ts += timedelta(hours=1)

        return predictions
