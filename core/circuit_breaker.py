"""
Circuit breaker pattern for LLM and external service resilience.
"""
import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TypeVar

from core.exceptions import AgentFrameworkError
from core.logger import setup_logger

logger = setup_logger("CircuitBreaker")

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = auto()      # Normal operation
    OPEN = auto()        # Failing fast
    HALF_OPEN = auto()   # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Fails fast when consecutive failures exceed threshold.
    Automatically probes recovery after timeout.
    """
    name: str = "default"
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 2

    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _failures: int = field(default=0, repr=False)
    _last_failure_time: float | None = field(default=None, repr=False)
    _half_open_calls: int = field(default=0, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, coro_factory: Callable[[], Awaitable[T]]) -> T:
        """
        Execute coro_factory() under circuit breaker protection.
        coro_factory must be a callable that returns a coroutine (not the coroutine itself),
        to prevent coroutine scheduling before permission check.
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                # Type hint for mypy because _last_failure_time is Optional[float]
                last_time = self._last_failure_time or 0.0
                if time.time() - last_time > self.recovery_timeout:
                    logger.info("[CircuitBreaker:%s] Transition OPEN -> HALF_OPEN", self.name)
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN. "
                        f"Retry after {self.recovery_timeout}s."
                    )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' HALF_OPEN limit reached."
                    )
                self._half_open_calls += 1

        # Execute outside lock to allow concurrency
        try:
            result = await coro_factory()
            await self._on_success()
            return result
        except Exception:
            await self._on_failure()
            raise

    async def _on_success(self):
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("[CircuitBreaker:%s] Recovery confirmed. HALF_OPEN -> CLOSED", self.name)
                self._state = CircuitState.CLOSED
                self._half_open_calls = 0
            self._failures = 0
            self._last_failure_time = None

    async def _on_failure(self):
        async with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()

            if self._failures >= self.failure_threshold and self._state != CircuitState.OPEN:
                logger.error(
                    "[CircuitBreaker:%s] Threshold reached (%s/%s). Transition -> OPEN",
                    self.name, self._failures, self.failure_threshold
                )
                self._state = CircuitState.OPEN


class CircuitBreakerOpenError(AgentFrameworkError):
    """Raised when circuit breaker is OPEN or HALF_OPEN saturated."""
    pass
