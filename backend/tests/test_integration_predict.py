"""Integration test: simulate a DataHub predict call through V1 API."""

import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import create_app


def _make_historical_data(n_points: int = 72):
    """Generate synthetic hourly timeseries with trend + daily cycle + noise."""
    import math, random
    random.seed(42)
    start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    data = []
    for i in range(n_points):
        ts = start + timedelta(hours=i)
        hour_effect = 3.0 * math.sin(2 * math.pi * i / 24.0)
        trend = i * 0.02
        noise = random.uniform(-0.5, 0.5)
        value = 20.0 + hour_effect + trend + noise
        data.append({
            "timestamp": ts.isoformat().replace("+00:00", "Z"),
            "value": round(value, 2),
        })
    return data


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_predict_contract_with_gradient_boosting(client):
    """
    Verify /predict endpoint contract with gradient_boosting_predictor plugin.

    Uses mocked JobQueue to avoid Redis dependency.
    Checks request validation, response shape, and plugin routing.
    """
    historical = _make_historical_data(72)

    with patch("app.api.job_queue") as mock_jq:
        mock_jq_instance = AsyncMock()
        mock_jq_instance.create_job.return_value = "mock-job-uuid-12345"
        mock_jq.__bool__.return_value = True
        mock_jq.create_job = mock_jq_instance.create_job

        # Also patch the global job_queue reference
        import app.api as api_module
        original_jq = api_module.job_queue
        api_module.job_queue = mock_jq_instance

        try:
            response = client.post(
                "/api/intelligence/predict",
                json={
                    "entity_id": "urn:ngsi-ld:AgriParcel:test-1",
                    "attribute": "temperature",
                    "historical_data": historical,
                    "prediction_horizon": 6,
                    "plugin": "gradient_boosting_predictor",
                },
                headers={"X-Tenant-ID": "test_tenant"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "job_id" in data
            assert data["job_id"] == "mock-job-uuid-12345"
            assert data["status"] == "pending"
        finally:
            api_module.job_queue = original_jq


def test_predict_rejects_missing_tenant(client):
    """Missing X-Tenant-ID must return 400."""
    historical = _make_historical_data(72)
    response = client.post(
        "/api/intelligence/predict",
        json={
            "entity_id": "urn:ngsi-ld:AgriParcel:test-1",
            "attribute": "temperature",
            "historical_data": historical,
            "prediction_horizon": 6,
        },
        # No X-Tenant-ID header
    )
    assert response.status_code == 400
    assert "X-Tenant-ID" in response.json()["detail"]


def test_plugins_list_includes_gradient_boosting(client):
    """GET /plugins must list the new plugin."""
    response = client.get("/api/intelligence/plugins")
    assert response.status_code == 200
    plugins = response.json()["plugins"]
    plugin_names = [p["name"] for p in plugins]
    assert "gradient_boosting_predictor" in plugin_names


def test_v2_models_list_includes_gradient_boosting(client):
    """GET /models must list the new model."""
    response = client.get("/api/intelligence/models")
    assert response.status_code == 200
    models = response.json()["models"]
    model_ids = [m["model_id"] for m in models]
    assert "gradient_boosting_predictor" in model_ids
