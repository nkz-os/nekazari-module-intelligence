"""V2 worker tasks must never emit placeholder inference values."""

from unittest.mock import patch

import pytest

from app import tasks


def test_run_inference_refuses_unavailable_model_without_caching():
    with patch.object(tasks, "_get_fast_cache_sync") as get_cache:
        with pytest.raises(tasks.ModelNotAvailableError):
            tasks.run_lstm_inference.run(
                model_id="olive_lstm_yield_v1",
                features={"temp_max": 30.0, "soil_moisture": 0.15, "shade_percentage": 65.0},
                target_key="tracker-a",
            )
    get_cache.assert_not_called()


def test_no_precomputation_schedule():
    assert not tasks.celery_app.conf.beat_schedule
    assert not hasattr(tasks, "trigger_precomputation_batch")
