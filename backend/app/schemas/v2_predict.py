"""
V2 canonical predict: model_id + features + execution_mode.

Feature validation is model-dependent; invalid payloads yield 422 before enqueue (IMPLEMENTATION_REVIEW).
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Feature schemas per model (extend for new models)
class OliveYieldFeatures(BaseModel):
    """Features for olive_lstm_yield_v1."""
    temp_max: float
    soil_moisture: float
    shade_percentage: float = Field(..., ge=0, le=100)


class OliveQualityFeatures(BaseModel):
    """Features for olive_lstm_quality_v1."""
    dias_desde_cuajado: int = Field(..., ge=0)
    temp_min: float
    shade_percentage: float = Field(..., ge=0, le=100)


# Registry: model_id -> feature schema class (for validation and GET /models)
MODEL_REGISTRY: dict[str, type[BaseModel]] = {
    "olive_lstm_yield_v1": OliveYieldFeatures,
    "olive_lstm_quality_v1": OliveQualityFeatures,
}


def get_model_schema(model_id: str) -> type[BaseModel] | None:
    """Return the Pydantic model for the given model_id, or None if unknown."""
    return MODEL_REGISTRY.get(model_id)


def validate_features(model_id: str, features: dict[str, Any]) -> dict[str, Any]:
    """
    Validate features against the model's schema. Raises ValueError if invalid.
    Returns the validated feature dict (with coercion).
    """
    schema = get_model_schema(model_id)
    if not schema:
        raise ValueError(f"Unknown model_id: {model_id}")
    instance = schema.model_validate(features)
    return instance.model_dump()


def _default_cache_key(model_id: str, features: dict[str, Any]) -> str:
    """Build a cache key from model_id and features when not provided by client."""
    import hashlib
    blob = json.dumps({"model_id": model_id, "features": features}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


class PredictV2Request(BaseModel):
    """Canonical V2 predict request (validated before enqueue)."""
    model_id: str = Field(..., description="Registered model identifier")
    features: dict[str, Any] = Field(..., description="Feature vector; schema depends on model_id")
    execution_mode: Literal["background_cached", "on_demand_sync"] = Field(
        default="on_demand_sync",
        description="background_cached: return from cache or 202; on_demand_sync: wait for result",
    )
    cache_key: str | None = Field(
        default=None,
        description="Optional stable key for cache (e.g. tracker_id). If omitted, derived from model_id+features.",
    )

    @field_validator("model_id")
    @classmethod
    def model_id_registered(cls, v: str) -> str:
        if v not in MODEL_REGISTRY:
            raise ValueError(f"Unknown model_id: {v}. Registered: {list(MODEL_REGISTRY.keys())}")
        return v

    def validate_features_for_model(self) -> dict[str, Any]:
        """Validate self.features against self.model_id schema. Raises ValueError if invalid."""
        return validate_features(self.model_id, self.features)

    def get_cache_key(self, validated_features: dict[str, Any] | None = None) -> str:
        """Return cache key: self.cache_key if set, else derived from model_id + features."""
        if self.cache_key:
            return self.cache_key
        feats = validated_features if validated_features is not None else self.features
        return _default_cache_key(self.model_id, feats)


class PredictV2Response(BaseModel):
    """V2 predict response: either data (200) or task_id (202)."""
    status: Literal["success", "processing"]
    data: dict[str, Any] | None = None
    task_id: str | None = None
