"""
Intelligence Module Backend - API Routes

Main API router that includes all endpoint definitions.
V2 canonical predict and evaluate_status use Celery (send_task) and fast cache (Redis DB 2).
"""

import json
import logging
import asyncio
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.redis_client import redis_client, redis_client_fast_cache
from app.core.job_queue import JobQueue, JobStatus
from app.core.worker import IntelligenceWorker
from app.schemas.v2_predict import PredictV2Request, MODEL_REGISTRY

logger = logging.getLogger(__name__)

# Cache key prefix and TTL (must match worker write)
V2_CACHE_KEY_PREFIX = "intelligence:cache:"
V2_CACHE_TTL = 1800

# Router setup
router = APIRouter(tags=["Intelligence"])

# Global instances
job_queue: Optional[JobQueue] = None
worker: Optional[IntelligenceWorker] = None
worker_task: Optional[asyncio.Task] = None


# =============================================================================
# Request/Response Models
# =============================================================================

class AnalyzeRequest(BaseModel):
    """Request model for analysis endpoint."""
    entity_id: str = Field(..., description="Entity ID to analyze")
    attribute: str = Field(..., description="Attribute name to predict")
    historical_data: list = Field(..., description="Historical data points")
    prediction_horizon: int = Field(24, ge=1, le=168, description="Prediction horizon in hours (1-168)")
    plugin: str = Field("simple_predictor", description="Plugin to use for analysis")
    priority: int = Field(0, description="Job priority (higher = more urgent)")


class PredictRequestMetadataOnly(BaseModel):
    """Metadata-only predict (DataHub flow). Backend fetches historical data from timeseries-reader."""
    entity_id: str = Field(..., description="Entity ID to predict")
    attribute: str = Field(..., description="Attribute name (e.g. temp_avg)")
    start_time: str = Field(..., description="Start of range (ISO 8601)")
    end_time: str = Field(..., description="End of range (ISO 8601)")
    prediction_horizon: int = Field(24, ge=1, le=168, description="Horizon in hours")
    plugin: str = Field("simple_predictor", description="Plugin to use")


class PredictRequest(BaseModel):
    """Request model for prediction endpoint. Supports metadata-only (start_time/end_time) or legacy (historical_data)."""
    entity_id: str = Field(..., description="Entity ID to predict")
    attribute: str = Field(..., description="Attribute name to predict")
    start_time: Optional[str] = Field(None, description="If set with end_time, backend fetches data internally")
    end_time: Optional[str] = Field(None, description="End of range (ISO 8601)")
    historical_data: Optional[list] = Field(None, description="If omitted and start_time/end_time set, backend fetches")
    prediction_horizon: int = Field(24, ge=1, le=168, description="Prediction horizon in hours")
    plugin: str = Field("simple_predictor", description="Plugin to use")
    priority: int = Field(0, description="Job priority")


class WebhookRequest(BaseModel):
    """Request model for n8n webhook endpoint."""
    entity_id: Optional[str] = None
    attribute: Optional[str] = None
    analysis_type: str = Field("predict", description="Type of analysis to run")
    data: Dict[str, Any] = Field(default_factory=dict, description="Additional data")


# =============================================================================
# Initialization
# =============================================================================

async def initialize_worker():
    """Initialize job queue and worker."""
    global job_queue, worker, worker_task
    
    if job_queue is None:
        job_queue = JobQueue(redis_client.client)
        worker = IntelligenceWorker(job_queue)
        worker_task = asyncio.create_task(worker.run())


def extract_tenant_id(authorization: Optional[str] = None, x_tenant_id: Optional[str] = Header(None)) -> str:
    """Extract tenant ID from headers."""
    if x_tenant_id:
        return x_tenant_id
    return "default"


# =============================================================================
# Routes
# =============================================================================

@router.on_event("startup")
async def startup_event():
    """Initialize worker on startup."""
    await initialize_worker()


@router.post("/analyze")
async def trigger_analysis(
    request: AnalyzeRequest,
    x_tenant_id: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
):
    """
    Trigger an analysis job.
    
    Returns immediately with a job ID. Use GET /jobs/{job_id} to check status.
    """
    if not job_queue:
        await initialize_worker()
    
    tenant_id = extract_tenant_id(authorization, x_tenant_id)
    
    job_data = {
        "entity_id": request.entity_id,
        "attribute": request.attribute,
        "historical_data": request.historical_data,
        "prediction_horizon": request.prediction_horizon,
        "plugin": request.plugin,
        "priority": request.priority
    }
    
    job_id = await job_queue.create_job("analyze", job_data, tenant_id)
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Analysis job created"
    }


@router.post("/predict")
async def trigger_prediction(
    request: PredictRequest,
    x_tenant_id: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
):
    """
    Trigger a prediction job and write results to Orion-LD.

    Accepts metadata-only (start_time, end_time; no historical_data) or legacy (historical_data).
    When start_time and end_time are provided and historical_data is omitted, the worker fetches
    data internally from the platform timeseries-reader.
    """
    if not job_queue:
        await initialize_worker()

    tenant_id = extract_tenant_id(authorization, x_tenant_id)

    job_data: Dict[str, Any] = {
        "entity_id": request.entity_id,
        "attribute": request.attribute,
        "prediction_horizon": request.prediction_horizon,
        "plugin": request.plugin,
        "priority": request.priority,
    }
    if request.historical_data is not None:
        job_data["historical_data"] = request.historical_data
    if request.start_time is not None:
        job_data["start_time"] = request.start_time
    if request.end_time is not None:
        job_data["end_time"] = request.end_time

    job_id = await job_queue.create_job("predict", job_data, tenant_id)

    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Prediction job created. Results will be written to Orion-LD.",
    }


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status by ID."""
    if not job_queue:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    job = await job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "id": job["id"],
        "type": job["type"],
        "status": job["status"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "result": job.get("result"),
        "error": job.get("error")
    }


async def _stream_job_events(job_id: str):
    """Yield SSE events while job is pending/running; final event when completed/failed/cancelled."""
    if not job_queue:
        yield f"data: {json.dumps({'status': 'error', 'error': 'Service not ready'})}\n\n"
        return
    poll_interval = 0.5
    while True:
        job = await job_queue.get_job(job_id)
        if not job:
            yield f"data: {json.dumps({'status': 'error', 'error': 'Job not found'})}\n\n"
            return
        status = job.get("status", "pending")
        payload = {
            "status": status,
            "result": job.get("result"),
            "error": job.get("error"),
            "id": job.get("id"),
            "type": job.get("type"),
        }
        yield f"data: {json.dumps(payload)}\n\n"
        if status in ("completed", "failed", "cancelled"):
            return
        await asyncio.sleep(poll_interval)


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    """Server-Sent Events stream of job status. Use EventSource in the browser."""
    if not job_queue:
        raise HTTPException(status_code=503, detail="Service not ready")
    job = await job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StreamingResponse(
        _stream_job_events(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a pending job."""
    if not job_queue:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    success = await job_queue.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled or not found")
    
    return {"message": "Job cancelled successfully"}


@router.post("/webhook/n8n")
async def n8n_webhook(
    request: WebhookRequest,
    x_tenant_id: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
):
    """
    Webhook endpoint for n8n integration.
    
    Accepts webhook calls from n8n workflows and triggers analysis jobs.
    """
    if not job_queue:
        await initialize_worker()
    
    tenant_id = extract_tenant_id(authorization, x_tenant_id)
    
    # Extract entity_id and attribute from request
    entity_id = request.entity_id or request.data.get("entity_id")
    attribute = request.attribute or request.data.get("attribute")
    
    if not entity_id or not attribute:
        raise HTTPException(status_code=400, detail="entity_id and attribute are required")
    
    # Prepare job data
    job_data = {
        "entity_id": entity_id,
        "attribute": attribute,
        "historical_data": request.data.get("historical_data", []),
        "prediction_horizon": request.data.get("prediction_horizon", 24),
        "plugin": request.data.get("plugin", "simple_predictor"),
        "priority": request.data.get("priority", 0),
        **request.data
    }
    
    job_id = await job_queue.create_job(request.analysis_type, job_data, tenant_id)
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": f"{request.analysis_type} job created from webhook"
    }


@router.get("/plugins")
async def list_plugins():
    """List available analysis plugins."""
    if not worker:
        await initialize_worker()
    
    plugins = [
        {
            "name": name,
            "description": "Analysis plugin"
        }
        for name in worker.plugins.keys()
    ]
    
    return {"plugins": plugins}


# =============================================================================
# V2 Canonical API (model_id + features + execution_mode)
# =============================================================================

@router.get("/models", response_model=dict)
async def list_models():
    """
    List registered models (model_id, feature schema). For discovery and validation.
    """
    models = []
    for model_id, schema_cls in MODEL_REGISTRY.items():
        models.append({
            "model_id": model_id,
            "features_schema": schema_cls.model_json_schema(),
        })
    return {"models": models}


@router.post("/v2/predict")
async def predict_v2(payload: PredictV2Request):
    """
    Canonical V2 predict: model_id + features + execution_mode.
    Validates features against model schema (422 if invalid). Then cache read or enqueue.
    """
    try:
        validated_features = payload.validate_features_for_model()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    cache_key = payload.get_cache_key(validated_features)
    full_key = f"{V2_CACHE_KEY_PREFIX}{cache_key}"
    cache = redis_client_fast_cache.client
    if not cache:
        raise HTTPException(status_code=503, detail="Fast cache not connected")
    if payload.execution_mode == "background_cached":
        raw = await cache.get(full_key)
        if raw:
            try:
                data = json.loads(raw)
                return {"status": "success", "data": data}
            except json.JSONDecodeError:
                pass
        from app.celery_app import celery_app
        task = celery_app.send_task(
            "app.tasks.run_lstm_inference",
            kwargs={
                "model_id": payload.model_id,
                "features": validated_features,
                "target_key": cache_key,
            },
        )
        return {"status": "processing", "task_id": task.id}
    else:
        from app.celery_app import celery_app
        task = celery_app.send_task(
            "app.tasks.run_lstm_inference",
            kwargs={
                "model_id": payload.model_id,
                "features": validated_features,
                "target_key": cache_key,
            },
        )
        try:
            result = await asyncio.to_thread(task.get, timeout=5.0)
            return {"status": "success", "data": result}
        except Exception as e:
            logger.warning("V2 on_demand_sync timeout or error: %s", e)
            raise HTTPException(status_code=504, detail="Inference timeout")


class EvaluateStatusRequest(BaseModel):
    """Optional adapter: domain-specific payload (e.g. agrivoltaic telemetry)."""
    tracker_id: str = Field(..., description="Tracker identifier")
    parcel_id: str = Field(..., description="Parcel identifier")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    shadow_polygon_2d: list[Any] = Field(default_factory=list, description="Shadow geometry")
    telemetry: Dict[str, Any] = Field(default_factory=dict, description="Telemetry (soil_moisture, etc.)")


def _evaluate_status_to_features(body: EvaluateStatusRequest) -> tuple[str, dict[str, Any]]:
    """Map evaluate_status payload to model_id + features (stub: extend with real mapping)."""
    # Placeholder: derive features from telemetry and shadow; use olive_lstm_yield_v1
    telemetry = body.telemetry or {}
    shade_pct = 0.0
    if body.shadow_polygon_2d:
        # Stub: real impl would compute shade percentage from polygon
        shade_pct = 50.0
    features = {
        "temp_max": float(telemetry.get("temp_max", 25.0)),
        "soil_moisture": float(telemetry.get("soil_moisture", 0.2)),
        "shade_percentage": shade_pct,
    }
    return "olive_lstm_yield_v1", features


@router.post("/evaluate_status")
async def evaluate_status(request: EvaluateStatusRequest):
    """
    Optional adapter: map domain payload to model_id + features, read from cache only.
    Returns 200 + scalar bundle if cache hit; 200 + {} on miss (fail-safe for latency-sensitive callers).
    """
    model_id, features = _evaluate_status_to_features(request)
    cache_key = request.tracker_id
    full_key = f"{V2_CACHE_KEY_PREFIX}{cache_key}"
    cache = redis_client_fast_cache.client
    if not cache:
        return {}
    raw = await cache.get(full_key)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
    except (json.JSONDecodeError, TypeError):
        return {}


@router.get("/v2/jobs/{task_id}")
async def get_v2_task_status(task_id: str):
    """Poll Celery task status (when 202 was returned from POST /v2/predict)."""
    from app.celery_app import celery_app
    result = celery_app.AsyncResult(task_id)
    if result.ready():
        if result.successful():
            return {"status": "success", "data": result.result}
        return {"status": "failed", "error": str(result.result)}
    return {"status": "processing", "task_id": task_id}


