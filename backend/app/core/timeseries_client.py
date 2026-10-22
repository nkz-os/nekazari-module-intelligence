"""
Fetch historical timeseries from platform timeseries-reader (metadata-only predict).
Uses Apache Arrow IPC (zero-copy) and returns a pandas DataFrame.
Resolution is derived from prediction_horizon, not hardcoded.
CPU-bound Arrow/pandas work is offloaded to a thread pool to avoid blocking the event loop.
"""

import asyncio
import logging
from typing import Union

import httpx
import pyarrow as pa
import pandas as pd

logger = logging.getLogger(__name__)

ARROW_ACCEPT = "application/vnd.apache.arrow.stream"


def get_timeseries_reader_url() -> str:
    from app.config import get_settings
    return get_settings().timeseries_reader_url.rstrip("/")


def _parse_iso(s: str):
    from datetime import datetime, timezone
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def _resolution_from_horizon(
    prediction_horizon_hours: int,
    start_time: str,
    end_time: str,
    max_points: int = 10_000,
    min_points: int = 100,
) -> int:
    """
    Derive target number of points from prediction horizon and range.
    Avoids hardcoded resolution; roughly one point per hour over the horizon,
    capped to [min_points, max_points].
    """
    start = _parse_iso(start_time)
    end = _parse_iso(end_time)
    delta_hours = max(1, (end - start).total_seconds() / 3600)
    # Roughly hourly for the horizon, or one per (delta / horizon) to align with forecast step
    resolution = int(delta_hours * max(1, 24 / max(1, prediction_horizon_hours)))
    return max(min_points, min(max_points, resolution))


def _parse_arrow_to_pandas(payload: bytes) -> pd.DataFrame:
    """CPU-bound: parse Arrow IPC stream to pandas. Run in thread pool."""
    table = pa.ipc.open_stream(payload).read_all()
    return table.to_pandas()


async def fetch_historical_data(
    entity_id: str,
    attribute: str,
    start_time: str,
    end_time: str,
    tenant_id: str,
    prediction_horizon_hours: int = 24,
) -> pd.DataFrame:
    """
    Fetch timeseries from platform timeseries-reader as Arrow IPC stream.
    Converts to pandas DataFrame (timestamp + value). No JSON, no list of dicts.
    Resolution is computed from prediction_horizon and time range.
    """
    base = get_timeseries_reader_url()
    if not base:
        raise ValueError("TIMESERIES_READER_URL not configured")

    resolution = _resolution_from_horizon(prediction_horizon_hours, start_time, end_time)

    url = f"{base}/api/timeseries/entities/{entity_id}/data"
    params = {
        "start_time": start_time,
        "end_time": end_time,
        "resolution": resolution,
        "attribute": attribute,
        "format": "arrow",
    }
    headers = {
        "Fiware-Service": tenant_id,
        "Accept": ARROW_ACCEPT,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        body = resp.content

    # Offload CPU-bound task to thread pool to avoid blocking the event loop
    df = await asyncio.to_thread(_parse_arrow_to_pandas, body)
    if "timestamp" not in df.columns or "value" not in df.columns:
        raise ValueError("Arrow table must have 'timestamp' and 'value' columns")
    return df
