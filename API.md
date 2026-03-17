# Intelligence Module — API Reference

This document is the **canonical API contract** for the Intelligence module. Any platform module (frontends, backends, DataHub, n8n, ERP, agrivoltaic apps) should use this reference to integrate.

- **Base URL:** `{host}/api/intelligence` (e.g. `http://intelligence-api-service:8000/api/intelligence` in-cluster).
- **OpenAPI (live):** `GET {base}/docs`, `GET {base}/redoc`, `GET {base}/openapi.json`.

---

## V2 canonical API (preferred for new integrations)

### GET /api/intelligence/models

List registered models and their feature schemas. Use this to discover valid `model_id` values and the exact `features` shape required for each model.

**Response (200):**

```json
{
  "models": [
    {
      "model_id": "olive_lstm_yield_v1",
      "features_schema": { ... }
    },
    {
      "model_id": "olive_lstm_quality_v1",
      "features_schema": { ... }
    }
  ]
}
```

Each `features_schema` is a JSON Schema (Pydantic-generated) describing required/optional keys and types.

**Registered models (current):**

| model_id | Required features | Constraints |
|----------|-------------------|-------------|
| `olive_lstm_yield_v1` | `temp_max` (float), `soil_moisture` (float), `shade_percentage` (float) | `shade_percentage` in [0, 100] |
| `olive_lstm_quality_v1` | `dias_desde_cuajado` (int), `temp_min` (float), `shade_percentage` (float) | `dias_desde_cuajado` ≥ 0; `shade_percentage` in [0, 100] |

---

### POST /api/intelligence/v2/predict

Run inference with a registered model and a feature vector. The API **validates** `features` against the model schema **before** enqueuing; invalid payloads receive **422** and are never sent to the worker.

**Request body:**

```json
{
  "model_id": "olive_lstm_yield_v1",
  "features": {
    "temp_max": 35.2,
    "soil_moisture": 0.18,
    "shade_percentage": 75.0
  },
  "execution_mode": "background_cached",
  "cache_key": "optional_stable_key"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_id` | string | Yes | Must be a registered model (see GET /models). Unknown value → 422. |
| `features` | object | Yes | Feature vector; keys and types must match the model schema. Wrong key or type → 422. |
| `execution_mode` | string | No (default: `on_demand_sync`) | `background_cached` or `on_demand_sync`. |
| `cache_key` | string | No | Stable key for cache lookup/write (e.g. `tracker_id`). If omitted, derived from hash of `model_id` + `features`. |

**Responses:**

| Status | When | Body |
|--------|------|------|
| 200 | Cache hit (background_cached) or sync result (on_demand_sync) | `{"status": "success", "data": { ... }}` — scalar bundle (e.g. `stress_index`, `fruit_count_pred`, `oil_concentration_pred`). |
| 202 | background_cached and cache miss | `{"status": "processing", "task_id": "<celery_task_id>"}`. Poll GET /api/intelligence/v2/jobs/{task_id}. |
| 422 | Unknown `model_id` or `features` validation failed | `{"detail": "<error message>"}`. Request is rejected before any enqueue. |
| 503 | Fast cache (Redis DB 2) not connected | `{"detail": "Fast cache not connected"}`. |
| 504 | on_demand_sync: worker did not finish within timeout (5 s) | `{"detail": "Inference timeout"}`. |

---

### GET /api/intelligence/v2/jobs/{task_id}

Poll status of an async inference task (when POST /v2/predict returned 202).

**Response (200):**

- `{"status": "processing", "task_id": "..."}` — not ready yet.
- `{"status": "success", "data": { ... }}` — task completed; `data` is the scalar bundle.
- `{"status": "failed", "error": "..."}` — task failed.

---

## Optional adapter: evaluate_status

### POST /api/intelligence/evaluate_status

Domain-specific adapter for latency-sensitive callers (e.g. agrivoltaic /notify). Maps the request to an internal model + features and returns **from cache only**; it never runs inference in the request path. Use a short timeout (e.g. 200 ms) and treat empty response as fail-safe.

**Request body:**

```json
{
  "tracker_id": "tracker-001",
  "parcel_id": "parcel-abc",
  "timestamp": "2025-03-17T12:00:00Z",
  "shadow_polygon_2d": [],
  "telemetry": {
    "soil_moisture": 0.18,
    "temp_max": 32.0
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tracker_id` | string | Yes | Used as cache key; precomputation must write under this key for cache hit. |
| `parcel_id` | string | Yes | Identifies the parcel. |
| `timestamp` | string | Yes | ISO 8601. |
| `shadow_polygon_2d` | array | No | Shadow geometry (used to derive e.g. shade_percentage). |
| `telemetry` | object | No | Keys e.g. `soil_moisture`, `temp_max`; mapped to model features. |

**Response (200):**

- If cache hit: JSON object with numeric scalar fields only (e.g. `stress_index`, `fruit_count_pred`, `oil_concentration_pred`). All values are floats.
- If cache miss or error: empty object `{}`. Callers should use defaults (e.g. `var` with default in rules).

---

## Execution modes (V2)

| Mode | Behaviour | Typical use |
|------|-----------|-------------|
| `background_cached` | API reads from Redis DB 2 (fast cache). Hit → 200 + data. Miss → enqueue task, return 202 + task_id. | Low-latency reads (&lt; 50 ms when cache warm); precomputation fills cache. |
| `on_demand_sync` | Enqueue task and block until result (timeout 5 s). Return 200 + data or 504. | Fresh data on demand (e.g. ERP). |

---

## Legacy endpoints (V1)

Still supported; for new integrations prefer V2.

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/intelligence/analyze | Enqueue analysis job; returns job_id. |
| POST | /api/intelligence/predict | Enqueue prediction job (metadata-only or with historical_data); writes result to Orion-LD. |
| GET | /api/intelligence/jobs/{job_id} | Job status. |
| GET | /api/intelligence/jobs/{job_id}/stream | SSE stream of job status. |
| POST | /api/intelligence/webhook/n8n | Webhook for n8n. |
| GET | /api/intelligence/plugins | List analysis plugins. |

See OpenAPI (`/api/intelligence/docs`) for request/response schemas.

---

## Integration checklist (any platform module)

1. **Base URL:** Use the Intelligence service URL + `/api/intelligence` (e.g. from env or service discovery).
2. **Discovery:** Call **GET /api/intelligence/models** to get valid `model_id` and feature schemas.
3. **Canonical call:** Use **POST /api/intelligence/v2/predict** with `model_id`, `features`, and `execution_mode`. Ensure `features` match the schema to avoid 422.
4. **Fail-safe:** On timeout, 5xx, or empty evaluate_status response, do not hardcode keys; use defaults (e.g. `var` with default in rules).
