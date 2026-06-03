"""Tests for GradientBoostingPredictor plugin."""

import pytest
from datetime import datetime, timedelta, timezone

from app.plugins.gradient_boosting_predictor import (
    GradientBoostingPredictor,
    MIN_TRAIN_POINTS,
)


def _make_historical_data(n_points: int = 48, base_value: float = 20.0):
    """Generate synthetic hourly timeseries with trend + daily cycle + noise."""
    import math, random
    random.seed(42)
    start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    data = []
    for i in range(n_points):
        ts = start + timedelta(hours=i)
        # Daily cycle: warmer during day (sin wave), small upward trend
        hour_effect = 3.0 * math.sin(2 * math.pi * i / 24.0)
        trend = i * 0.02
        noise = random.uniform(-0.5, 0.5)
        value = base_value + hour_effect + trend + noise
        data.append({
            "timestamp": ts.isoformat().replace("+00:00", "Z"),
            "value": round(value, 2),
        })
    return data


@pytest.mark.asyncio
async def test_predictor_name():
    """Plugin name must be consistent."""
    p = GradientBoostingPredictor()
    assert p.name == "gradient_boosting_predictor"


@pytest.mark.asyncio
async def test_rejects_insufficient_data():
    """Must raise ValueError if fewer than MIN_TRAIN_POINTS data points."""
    p = GradientBoostingPredictor()
    data = {
        "entity_id": "test:1",
        "attribute": "temp",
        "historical_data": _make_historical_data(10),  # < 24
        "prediction_horizon": 24,
    }
    with pytest.raises(ValueError, match=f"{MIN_TRAIN_POINTS}"):
        await p.analyze(data)


@pytest.mark.asyncio
async def test_produces_predictions_with_correct_shape():
    """Must produce exactly prediction_horizon predictions."""
    p = GradientBoostingPredictor()
    data = {
        "entity_id": "test:1",
        "attribute": "temp",
        "historical_data": _make_historical_data(72),
        "prediction_horizon": 6,
    }
    result = await p.analyze(data)
    assert "predictions" in result
    assert len(result["predictions"]) == 6
    for pred in result["predictions"]:
        assert "timestamp" in pred
        assert "value" in pred
        assert isinstance(pred["value"], (int, float))


@pytest.mark.asyncio
async def test_predictions_are_in_future():
    """All predictions must have timestamps after the last historical point."""
    p = GradientBoostingPredictor()
    historical = _make_historical_data(72)
    last_ts = historical[-1]["timestamp"]
    data = {
        "entity_id": "test:1",
        "attribute": "temp",
        "historical_data": historical,
        "prediction_horizon": 3,
    }
    result = await p.analyze(data)
    for pred in result["predictions"]:
        assert pred["timestamp"] > last_ts


@pytest.mark.asyncio
async def test_confidence_in_range():
    """Confidence must be between 0 and 1."""
    p = GradientBoostingPredictor()
    data = {
        "entity_id": "test:1",
        "attribute": "temp",
        "historical_data": _make_historical_data(72),
        "prediction_horizon": 24,
    }
    result = await p.analyze(data)
    assert 0.0 <= result["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_metadata_present():
    """Result must include metadata with data_points and train_score."""
    p = GradientBoostingPredictor()
    data = {
        "entity_id": "test:1",
        "attribute": "temp",
        "historical_data": _make_historical_data(48),
        "prediction_horizon": 12,
    }
    result = await p.analyze(data)
    assert "metadata" in result
    assert "data_points" in result["metadata"]
    assert result["metadata"]["data_points"] == 48
    assert "train_score" in result["metadata"]


@pytest.mark.asyncio
async def test_time_features_cyclical():
    """Sin/cos encodings must be in [-1, 1] range."""
    p = GradientBoostingPredictor()
    dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    feats = p._time_features(dt)
    assert len(feats) == 6
    for f in feats:
        assert -1.0 <= f <= 1.0


@pytest.mark.asyncio
async def test_build_features_dimensions():
    """Feature matrix must have correct number of columns (6 time + 6 lag/rolling = 12)."""
    import numpy as np
    data = _make_historical_data(72)
    timestamps = []
    values = []
    for point in data:
        ts_str = point["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        timestamps.append(dt)
        values.append(float(point["value"]))
    p = GradientBoostingPredictor()
    X, y = p._build_features(
        np.array(timestamps, dtype=object),
        np.array(values, dtype=np.float64),
    )
    assert X.shape[1] == 12  # 6 time features + 6 lag/rolling features
    assert len(y) > 0
    assert X.shape[0] == len(y)


@pytest.mark.asyncio
async def test_recursive_forecast_length():
    """Recursive forecast must produce exactly horizon predictions."""
    import numpy as np
    from sklearn.ensemble import GradientBoostingRegressor
    data = _make_historical_data(72)
    timestamps = []
    values = []
    for point in data:
        ts_str = point["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        timestamps.append(dt)
        values.append(float(point["value"]))
    ts_arr = np.array(timestamps, dtype=object)
    val_arr = np.array(values, dtype=np.float64)
    p = GradientBoostingPredictor()
    X, y = p._build_features(ts_arr, val_arr)
    model = GradientBoostingRegressor(n_estimators=10, max_depth=3, random_state=42)
    model.fit(X, y)
    horizon = 5
    preds = p._recursive_forecast(model, ts_arr, val_arr, timestamps[-1], horizon)
    assert len(preds) == horizon
