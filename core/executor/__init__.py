"""
Executor package — Strategy-pattern decomposition of the monolithic Executor.

Backward compatibility:
    ``from core.executor import Executor``
    still works and returns the ExecutorDispatcher class.
"""
from .dispatcher import ExecutorDispatcher

# Re-export as "Executor" so every existing import keeps working unchanged.
Executor = ExecutorDispatcher

__all__ = ["Executor", "ExecutorDispatcher"]
