"""Tests for Orion-LD client — NGSI-LD core context fallback."""

import os
from unittest.mock import patch, AsyncMock
import pytest
from app.core.orion_client import (
    NGSI_LD_CORE_CONTEXT,
    create_prediction_entity,
    inject_fiware_headers,
)


def test_ngsi_ld_core_context_constant():
    """The core context URL must point to the ETSI standard."""
    assert NGSI_LD_CORE_CONTEXT.startswith("https://uri.etsi.org/")
    assert "ngsi-ld" in NGSI_LD_CORE_CONTEXT


def test_inject_fiware_headers_includes_tenant():
    """Headers must include both NGSILD-Tenant and Fiware-Service."""
    headers = {}
    result = inject_fiware_headers(headers, tenant_id="My-Tenant")
    assert result["NGSILD-Tenant"] == "my_tenant"
    assert result["Fiware-Service"] == "my_tenant"
    assert result["Fiware-ServicePath"] == "/"
    assert result["Content-Type"] == "application/ld+json"


def test_inject_fiware_headers_with_custom_context():
    """When context_url is provided, use it in Link header."""
    headers = {}
    result = inject_fiware_headers(
        headers, tenant_id="test", context_url="https://example.com/context.json"
    )
    assert "Link" in result
    assert "example.com/context.json" in result["Link"]


@pytest.mark.asyncio
async def test_create_prediction_entity_with_context_fallback():
    """When CONTEXT_URL is empty, use the NGSI-LD core context."""
    with patch.dict(os.environ, {"CONTEXT_URL": ""}):
        with patch("app.core.orion_client.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.post.return_value.status_code = 201
            mock_client.return_value = mock_instance

            result = await create_prediction_entity(
                entity_id="urn:ngsi-ld:Prediction:test:test-123",
                tenant_id="test_tenant",
                ref_entity_id="urn:ngsi-ld:AgriParcel:parcel-1",
                predicted_attribute="temperature",
                predictions=[{"timestamp": "2024-01-01T00:00:00Z", "value": 25.0}],
                model="simple_predictor",
                confidence=0.9,
            )

            assert result is not None
            # Verify the request body included the core context
            call_args = mock_instance.post.call_args
            sent_body = call_args[1]["json"]
            assert "@context" in sent_body
            assert NGSI_LD_CORE_CONTEXT in sent_body["@context"]
