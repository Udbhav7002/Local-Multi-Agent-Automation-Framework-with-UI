"""
Event Bus module for decoupled communication between components.
Implements the Observer pattern.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Any


@dataclass
class SystemEvent:
    """Base class for all system events."""
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "System"
    level: str = "INFO"
    payload: Dict[str, Any] = field(default_factory=dict)
    message: str = ""

@dataclass
class TaskStartedEvent(SystemEvent):
    """Fired when a new user task begins processing."""
    task_description: str = ""

@dataclass
class StepExecutedEvent(SystemEvent):
    """Fired when an individual step (CLI, GUI, Browser) is executed."""
    step_action: str = ""
    step_target: str = ""
    success: bool = False
    feedback: str = ""

@dataclass
class TaskCompletedEvent(SystemEvent):
    """Fired when the entire user task is completed or failed."""
    task_description: str = ""
    success: bool = False
    total_duration_s: float = 0.0
class EventBus:
    """
    Central event bus for the framework.
    Allows decoupling of logging, WebSockets, and inter-agent messaging.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[SystemEvent], None]]] = {}

    def subscribe(self, event_type: str, callback: Callable[[SystemEvent], None]) -> None:
        """Subscribe a callback to a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[[SystemEvent], None]) -> None:
        """Unsubscribe a callback from an event type."""
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
            except ValueError:
                pass

    def publish(self, event_type: str, event: SystemEvent) -> None:
        """Publish an event to all subscribers synchronously."""
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                try:
                    callback(event)
                except Exception as e:
                    # Catch all so one broken subscriber doesn't crash the bus
                    print(f"EventBus error notifying subscriber: {e}")

    async def publish_async(self, event_type: str, event: SystemEvent) -> None:
        """Publish an event, awaiting async subscribers."""
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    print(f"EventBus error notifying async subscriber: {e}")

