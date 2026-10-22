"""
Intelligence Module - API Tests

Basic test suite for API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data
    assert "version" in data


def test_list_plugins(client):
    """Test plugins listing endpoint."""
    response = client.get("/api/intelligence/plugins")
    assert response.status_code == 200
    data = response.json()
    assert "plugins" in data
    assert isinstance(data["plugins"], list)


def test_evaluate_status_rejects_oversized_polygon(client):
    """evaluate_status must reject polygons exceeding max_length=10000."""
    huge_polygon = [[0.0, 0.0]] * 10001  # 10,001 points -> exceeds max_length
    response = client.post(
        "/api/intelligence/evaluate_status",
        json={
            "tracker_id": "t-001",
            "parcel_id": "p-001",
            "timestamp": "2025-03-17T12:00:00Z",
            "shadow_polygon_2d": huge_polygon,
            "telemetry": {},
        },
    )
    assert response.status_code == 422




def test_models_report_unavailable(client):
    """Registered models without a deployed implementation are flagged unavailable."""
    response = client.get("/api/intelligence/models")
    assert response.status_code == 200
    assert all(m["available"] is False for m in response.json()["models"])


def test_v2_predict_unavailable_model_returns_503(client):
    """An unavailable model must fail explicitly, never return placeholder values."""
    response = client.post(
        "/api/intelligence/v2/predict",
        json={
            "model_id": "olive_lstm_yield_v1",
            "features": {"temp_max": 30.0, "soil_moisture": 0.15, "shade_percentage": 65.0},
            "execution_mode": "on_demand_sync",
        },
    )
    assert response.status_code == 503
    assert "not available" in response.json()["detail"]
