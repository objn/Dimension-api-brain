"""
Task Registry - Maps job_type to executable task functions.

Services register their task functions at application startup.
The JobDaemon uses this registry to find which function to run for each job_type.

Design:
    - TaskRegistry is a singleton
    - Each job_type maps to ONE callable(JobContext) -> Any
    - The callable reads its parameters from ctx.metadata
    - Registration happens in main.py startup, NOT in the service modules
"""
from typing import Dict, Callable, Any, Optional, List
import logging

from src.services.job_service import JobContext

logger = logging.getLogger(__name__)


class TaskRegistry:
    """
    Registry mapping job_type strings to task callable functions.
    
    Usage:
        registry = TaskRegistry()
        registry.register("node_content_embedding", embedding_task_func)
        
        func = registry.get("node_content_embedding")
        if func:
            result = await func(context)
    """
    
    _instance: Optional['TaskRegistry'] = None
    
    def __new__(cls) -> 'TaskRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._registry: Dict[str, Callable[[JobContext], Any]] = {}
        logger.info("TaskRegistry initialized")
    
    def register(self, job_type: str, task_func: Callable[[JobContext], Any]) -> None:
        """
        Register a task function for a job type.
        
        Args:
            job_type: Job type identifier (e.g. 'node_content_embedding')
            task_func: Callable that accepts JobContext and executes the task.
                       Can be sync or async. Reads parameters from ctx.metadata.
        """
        if job_type in self._registry:
            logger.warning(f"Overwriting existing task for job_type: {job_type}")
        self._registry[job_type] = task_func
        logger.info(f"Registered task for job_type: {job_type}")
    
    def get(self, job_type: str) -> Optional[Callable[[JobContext], Any]]:
        """Get task function for a job type. Returns None if not registered."""
        return self._registry.get(job_type)
    
    def has(self, job_type: str) -> bool:
        """Check if a job type has a registered task function."""
        return job_type in self._registry
    
    def list_types(self) -> List[str]:
        """List all registered job types."""
        return list(self._registry.keys())


# Global singleton
task_registry = TaskRegistry()
