"""Tests for tenant ID extraction — ensures missing tenant is rejected."""

import pytest
from fastapi import HTTPException
from app.api import extract_tenant_id


def test_extract_tenant_id_with_header():
    """When X-Tenant-ID is present, return it."""
    result = extract_tenant_id(x_tenant_id="my-tenant")
    assert result == "my-tenant"


def test_extract_tenant_id_missing_raises_400():
    """When X-Tenant-ID is missing, raise HTTP 400."""
    with pytest.raises(HTTPException) as exc_info:
        extract_tenant_id(x_tenant_id=None)
    assert exc_info.value.status_code == 400
    assert "X-Tenant-ID" in exc_info.value.detail


def test_extract_tenant_id_empty_string_raises_400():
    """Empty string is falsy — should be rejected same as missing header."""
    with pytest.raises(HTTPException) as exc_info:
        extract_tenant_id(x_tenant_id="")
    assert exc_info.value.status_code == 400
