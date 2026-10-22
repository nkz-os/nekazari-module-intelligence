#!/usr/bin/env python3
# =============================================================================
# Job Queue - Redis-based Async Job Processing
# =============================================================================
# Handles job queueing and status tracking for async analysis tasks.

import logging
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from enum import Enum
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobQueue:
    """Redis-based job queue for async processing."""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.job_prefix = "intelligence:job:"
        self.queue_key = "intelligence:queue"
        self.ttl_seconds = 86400 * 7  # 7 days
    
    async def create_job(
        self,
        job_type: str,
        job_data: Dict[str, Any],
        tenant_id: str
    ) -> str:
        """
        Create a new job and add it to the queue.
        
        Args:
            job_type: Type of job (e.g., "analyze", "predict")
            job_data: Job-specific data
            tenant_id: Tenant ID
            
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        job_key = f"{self.job_prefix}{job_id}"
        
        job = {
            "id": job_id,
            "type": job_type,
            "tenant_id": tenant_id,
            "status": JobStatus.PENDING.value,
            "data": job_data,
            "created_at": datetime.utcnow().isoformat() + 'Z',
            "updated_at": datetime.utcnow().isoformat() + 'Z',
            "result": None,
            "error": None,
            "retry_count": 0
        }
        
        # Store job in Redis
        await self.redis.setex(
            job_key,
            self.ttl_seconds,
            json.dumps(job)
        )
        
        # Add to queue
        queue_item = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "priority": job_data.get("priority", 0)
        }
        await self.redis.lpush(self.queue_key, json.dumps(queue_item))
        
        logger.info(f"Created job {job_id} of type {job_type} for tenant {tenant_id}")
        return job_id
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID."""
        job_key = f"{self.job_prefix}{job_id}"
        job_data = await self.redis.get(job_key)
        
        if job_data:
            return json.loads(job_data)
        return None
    
    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> bool:
        """Update job status and result/error."""
        job = await self.get_job(job_id)
        if not job:
            return False
        
        job["status"] = status.value
        job["updated_at"] = datetime.utcnow().isoformat() + 'Z'
        
        if result is not None:
            job["result"] = result
        if error is not None:
            job["error"] = error
            job["retry_count"] = job.get("retry_count", 0) + 1
        
        job_key = f"{self.job_prefix}{job_id}"
        await self.redis.setex(
            job_key,
            self.ttl_seconds,
            json.dumps(job)
        )
        
        logger.info(f"Updated job {job_id} status to {status.value}")
        return True
    
    async def get_next_job(self) -> Optional[Dict[str, Any]]:
        """Get next job from queue (blocks until available)."""
        # Simple implementation: get from right end (FIFO)
        queue_item_data = await self.redis.brpop(self.queue_key, timeout=5)
        
        if queue_item_data:
            queue_item = json.loads(queue_item_data[1])
            job_id = queue_item["job_id"]
            job = await self.get_job(job_id)
            return job
        
        return None
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job."""
        job = await self.get_job(job_id)
        if not job:
            return False
        
        if job["status"] in [JobStatus.PENDING, JobStatus.RUNNING]:
            await self.update_job_status(job_id, JobStatus.CANCELLED)
            return True
        
        return False

