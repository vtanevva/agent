"""
Background Job Handler for Memory System

Provides async execution for:
- Fact extraction
- Thread summarization
- Document processing

Uses a simple thread-based queue for MVP.
In production, replace with Celery/RQ.
"""

import logging
import queue
import threading
from typing import Callable, Any, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Job:
    """Background job"""
    job_id: str
    func: Callable
    args: tuple
    kwargs: dict
    created_at: datetime


class BackgroundJobQueue:
    """
    Simple background job queue using threads.
    
    TODO: Replace with Celery or RQ for production.
    """
    
    def __init__(self, num_workers: int = 2):
        """
        Initialize job queue.
        
        Args:
            num_workers: Number of worker threads
        """
        self.queue = queue.Queue()
        self.num_workers = num_workers
        self.workers = []
        self.running = False
        
    def start(self):
        """Start worker threads"""
        if self.running:
            return
        
        self.running = True
        
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker,
                name=f"MemoryWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
        
        logger.info(f"✅ Started {self.num_workers} background workers")
    
    def stop(self):
        """Stop worker threads"""
        self.running = False
        
        # Add stop signals
        for _ in range(self.num_workers):
            self.queue.put(None)
        
        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=5)
        
        self.workers = []
        logger.info("🛑 Stopped background workers")
    
    def _worker(self):
        """Worker thread loop"""
        while self.running:
            try:
                job = self.queue.get(timeout=1)
                
                if job is None:  # Stop signal
                    break
                
                # Execute job
                try:
                    logger.debug(f"⚙️ Executing job: {job.job_id}")
                    job.func(*job.args, **job.kwargs)
                    logger.debug(f"✅ Completed job: {job.job_id}")
                except Exception as e:
                    logger.error(f"❌ Job failed: {job.job_id} - {e}")
                
                self.queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker error: {e}")
    
    def enqueue(
        self,
        func: Callable,
        *args,
        job_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Enqueue a job for background execution.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            job_id: Job ID (auto-generated if not provided)
            **kwargs: Keyword arguments
        
        Returns:
            Job ID
        """
        from uuid import uuid4
        
        if not self.running:
            self.start()
        
        job_id = job_id or f"job-{uuid4().hex[:8]}"
        
        job = Job(
            job_id=job_id,
            func=func,
            args=args,
            kwargs=kwargs,
            created_at=datetime.utcnow(),
        )
        
        self.queue.put(job)
        logger.debug(f"📥 Enqueued job: {job_id}")
        
        return job_id


# Global job queue instance
_job_queue: Optional[BackgroundJobQueue] = None


def get_job_queue() -> BackgroundJobQueue:
    """Get singleton job queue instance"""
    global _job_queue
    if _job_queue is None:
        _job_queue = BackgroundJobQueue(num_workers=2)
        _job_queue.start()
    return _job_queue


def async_extract_facts(user_id: str, text: str, source_ref: str):
    """
    Enqueue fact extraction job.
    
    Args:
        user_id: User ID
        text: Text to extract facts from
        source_ref: Source reference
    """
    from .ingestion_service import get_ingestion_service
    
    def _extract():
        ingestion_service = get_ingestion_service()
        ingestion_service._extract_and_store_facts(user_id, text, source_ref)
    
    job_queue = get_job_queue()
    job_queue.enqueue(_extract, job_id=f"extract-facts-{source_ref}")


def async_update_thread_summary(user_id: str, thread_id: str):
    """
    Enqueue thread summary update job.
    
    Args:
        user_id: User ID
        thread_id: Thread ID
    """
    from .ingestion_service import get_ingestion_service
    
    def _update():
        ingestion_service = get_ingestion_service()
        ingestion_service.update_thread_summary(user_id, thread_id)
    
    job_queue = get_job_queue()
    job_queue.enqueue(_update, job_id=f"summary-{thread_id}")


def async_index_document(
    user_id: str,
    file_path: str,
    title: str,
    **kwargs
):
    """
    Enqueue document indexing job.
    
    Args:
        user_id: User ID
        file_path: Path to document
        title: Document title
        **kwargs: Additional arguments for ingest_document
    """
    from .ingestion_service import get_ingestion_service
    
    def _index():
        ingestion_service = get_ingestion_service()
        ingestion_service.ingest_document(
            user_id=user_id,
            file_path=file_path,
            title=title,
            **kwargs
        )
    
    job_queue = get_job_queue()
    job_queue.enqueue(_index, job_id=f"index-doc-{title}")


# Cleanup on module unload
import atexit

def _cleanup():
    """Stop job queue on exit"""
    global _job_queue
    if _job_queue is not None:
        _job_queue.stop()

atexit.register(_cleanup)

