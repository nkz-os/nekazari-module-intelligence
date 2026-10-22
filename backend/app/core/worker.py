#!/usr/bin/env python3
# =============================================================================
# Worker - Async Job Processor
# =============================================================================
# Processes jobs from the queue and executes analysis plugins.

import logging
import asyncio
from typing import Dict, Any
from app.core.job_queue import JobQueue, JobStatus
from app.core.orion_client import create_prediction_entity
from app.core.timeseries_client import fetch_historical_data
from app.plugins.simple_predictor import SimplePredictor
from app.plugins.gradient_boosting_predictor import GradientBoostingPredictor

logger = logging.getLogger(__name__)


class IntelligenceWorker:
    """Worker that processes jobs from the queue."""
    
    def __init__(self, job_queue: JobQueue):
        self.job_queue = job_queue
        self.plugins = {
            "simple_predictor": SimplePredictor(),
            "gradient_boosting_predictor": GradientBoostingPredictor(),
        }
        self.running = False
    
    async def process_job(self, job: Dict[str, Any]) -> None:
        """Process a single job."""
        job_id = job["id"]
        job_type = job["type"]
        tenant_id = job["tenant_id"]
        job_data = job["data"]
        
        try:
            # Update status to running
            await self.job_queue.update_job_status(job_id, JobStatus.RUNNING)
            
            logger.info(f"Processing job {job_id} of type {job_type}")
            
            # Route to appropriate handler
            if job_type == "analyze":
                result = await self._handle_analyze(job_data, tenant_id)
            elif job_type == "predict":
                result = await self._handle_predict(job_data, tenant_id)
            else:
                raise ValueError(f"Unknown job type: {job_type}")
            
            # Update job as completed
            await self.job_queue.update_job_status(job_id, JobStatus.COMPLETED, result=result)
            logger.info(f"Job {job_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}", exc_info=True)
            await self.job_queue.update_job_status(
                job_id,
                JobStatus.FAILED,
                error=str(e)
            )
    
    async def _handle_analyze(self, data: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
        """Handle analysis job."""
        plugin_name = data.get("plugin", "simple_predictor")
        plugin = self.plugins.get(plugin_name)
        
        if not plugin:
            raise ValueError(f"Plugin not found: {plugin_name}")
        
        result = await plugin.analyze(data)
        return result
    
    async def _handle_predict(self, data: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
        """Handle prediction job and write to Orion-LD."""
        # Metadata-only: fetch historical_data from timeseries-reader if start_time/end_time set
        if not data.get("historical_data") and data.get("start_time") and data.get("end_time"):
            try:
                data["historical_data"] = await fetch_historical_data(
                    entity_id=data["entity_id"],
                    attribute=data["attribute"],
                    start_time=data["start_time"],
                    end_time=data["end_time"],
                    tenant_id=tenant_id,
                    prediction_horizon_hours=data.get("prediction_horizon", 24),
                )
            except Exception as e:
                logger.error(f"Failed to fetch historical data from timeseries-reader: {e}", exc_info=True)
                raise ValueError(f"Cannot fetch historical data: {e}") from e
        # Run analysis
        analysis_result = await self._handle_analyze(data, tenant_id)
        
        # Write prediction to Orion-LD
        entity_id = data.get("entity_id")
        predicted_attribute = data.get("attribute", "value")
        predictions = analysis_result.get("predictions", [])
        model = analysis_result.get("model", "simple_predictor")
        confidence = analysis_result.get("confidence", 0.5)
        
        # Generate prediction entity ID
        prediction_id = f"urn:ngsi-ld:Prediction:{tenant_id}:{entity_id.split(':')[-1]}-{predicted_attribute}"
        
        orion_result = await create_prediction_entity(
            entity_id=prediction_id,
            tenant_id=tenant_id,
            ref_entity_id=entity_id,
            predicted_attribute=predicted_attribute,
            predictions=predictions,
            model=model,
            confidence=confidence
        )
        
        return {
            **analysis_result,
            "orion_entity_id": orion_result
        }
    
    async def run(self) -> None:
        """Main worker loop."""
        self.running = True
        logger.info("Intelligence worker started")
        
        while self.running:
            try:
                job = await self.job_queue.get_next_job()
                if job:
                    await self.process_job(job)
                else:
                    # No jobs available, wait a bit
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    def stop(self) -> None:
        """Stop the worker."""
        self.running = False
        logger.info("Intelligence worker stopped")

