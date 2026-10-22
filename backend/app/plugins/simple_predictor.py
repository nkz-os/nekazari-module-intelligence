#!/usr/bin/env python3
# =============================================================================
# Simple Predictor Plugin - Placeholder for ML models
# =============================================================================
# This is a simple plugin that demonstrates the architecture.
# In production, this would be replaced with actual ML models (scikit-learn, etc.)

import logging
from typing import Dict, Any, List, Union
from datetime import datetime, timedelta, timezone
from app.plugins.base import IntelligencePlugin

logger = logging.getLogger(__name__)


def _historical_to_values_and_last_ts(historical_data: Union[List[Dict[str, Any]], "pd.DataFrame"]):
    """Normalize historical_data (DataFrame or list of dicts) to (values list, last_timestamp)."""
    try:
        import pandas as pd
    except ImportError:
        pd = None
    if pd is not None and isinstance(historical_data, pd.DataFrame):
        values = historical_data["value"].astype(float).tolist()
        ts = historical_data["timestamp"]
        last_ts = ts.iloc[-1]
        if hasattr(last_ts, "timestamp"):
            last_dt = last_ts.to_pydatetime() if hasattr(last_ts, "to_pydatetime") else datetime.fromtimestamp(float(last_ts), tz=timezone.utc)
        else:
            last_dt = datetime.fromtimestamp(float(last_ts), tz=timezone.utc)
        return values, last_dt
    # list of dicts
    values = [float(p["value"]) for p in historical_data]
    last_ts_str = historical_data[-1]["timestamp"]
    last_dt = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
    return values, last_dt


class SimplePredictor(IntelligencePlugin):
    """
    Simple predictor plugin that generates basic linear predictions.
    
    This is a placeholder that demonstrates the plugin architecture.
    In production, replace with actual ML models.
    """
    
    @property
    def name(self) -> str:
        return "simple_predictor"
    
    async def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze data and generate predictions.
        
        Expected data format:
        {
            "entity_id": "urn:ngsi-ld:AgriSensor:sensor-123",
            "attribute": "temperature",
            "historical_data": [
                {"timestamp": "2024-01-15T10:00:00Z", "value": 20.5},
                {"timestamp": "2024-01-15T11:00:00Z", "value": 22.1},
                ...
            ],
            "prediction_horizon": 24  # hours
        }
        
        Returns:
        {
            "predictions": [
                {"timestamp": "2024-01-16T10:00:00Z", "value": 23.5},
                ...
            ],
            "confidence": 0.75,
            "model": "simple_predictor"
        }
        """
        try:
            historical_data = data.get("historical_data", [])
            if not hasattr(historical_data, "__len__") or len(historical_data) < 2:
                raise ValueError("Need at least 2 historical data points")
            
            values, last_timestamp = _historical_to_values_and_last_ts(historical_data)
            last_value = values[-1]

            attribute = data.get("attribute", "value")
            prediction_horizon = data.get("prediction_horizon", 24)  # hours
            
            # Simple linear trend calculation
            recent_trend = (values[-1] - values[0]) / len(values) if len(values) > 1 else 0
            
            # Generate predictions
            predictions: List[Dict[str, Any]] = []
            
            for hour in range(1, prediction_horizon + 1):
                prediction_time = last_timestamp + timedelta(hours=hour)
                # Simple linear extrapolation
                predicted_value = last_value + (recent_trend * hour)
                
                predictions.append({
                    "timestamp": prediction_time.isoformat().replace('+00:00', 'Z'),
                    "value": round(predicted_value, 2)
                })
            
            # Simple confidence calculation (degrades over time)
            confidence = max(0.5, 0.9 - (prediction_horizon / 100))
            
            n_points = len(values)
            return {
                "predictions": predictions,
                "confidence": round(confidence, 2),
                "model": "simple_predictor",
                "metadata": {
                    "trend": round(recent_trend, 4),
                    "data_points": n_points
                }
            }
            
        except Exception as e:
            logger.error(f"Error in SimplePredictor.analyze: {e}", exc_info=True)
            raise

