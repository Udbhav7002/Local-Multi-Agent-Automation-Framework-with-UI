"""
Shared retry/timeout logic for LLM clients.

Centralizes the retry, timeout, and exponential backoff logic used by
both OllamaClient and LiteLLMClient to avoid code duplication.
"""
import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TypeVar

from core.config import config
from core.exceptions import LLMTimeoutError
from core.logger import setup_logger

logger = setup_logger("LLMRetry")

T = TypeVar("T")


async def execute_with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    timeout_seconds: float | None = None,
    operation_name: str = "LLM call",
    retryable_exceptions: tuple = (ConnectionError, OSError),
) -> T:
    """
    Execute a coroutine with retry logic, timeout, and exponential backoff.

    Args:
        coro_factory: A callable that returns a coroutine (not the coroutine itself)
        max_retries: Maximum number of retry attempts
        timeout_seconds: Timeout for each attempt (uses config.llm_timeout_seconds if None)
        operation_name: Name for logging purposes
        retryable_exceptions: Exception types that trigger a retry

    Returns:
        The result of the successful coroutine execution

    Raises:
        LLMTimeoutError: If all attempts time out
        The last exception: If all retries are exhausted
    """
    if timeout_seconds is None:
        timeout_seconds = config.llm_timeout_seconds

    last_exception = None

    for attempt in range(max_retries):
        try:
            logger.debug("%s: attempt %d/%d", operation_name, attempt + 1, max_retries)

            if timeout_seconds:
                result = await asyncio.wait_for(coro_factory(), timeout=timeout_seconds)
            else:
                result = await coro_factory()

            return result

        except asyncio.TimeoutError:
            last_exception = LLMTimeoutError(
                f"{operation_name} timed out after {timeout_seconds}s "
                f"({max_retries} attempts)"
            )
            logger.error("%s timed out after %ss (attempt %d/%d)",
                         operation_name, timeout_seconds, attempt + 1, max_retries)

        except retryable_exceptions as e:
            last_exception = e
            wait_time = 2 ** attempt
            logger.warning(
                "%s error (attempt %d/%d): %s. Retrying in %ds...",
                operation_name, attempt + 1, max_retries, e, wait_time
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
                continue
            raise

        except Exception as e:
            # Non-retryable exception - re-raise immediately
            logger.error("%s failed with non-retryable error: %s", operation_name, e)
            raise

    # All retries exhausted
    if last_exception:
        raise last_exception
    raise RuntimeError(f"{operation_name} failed after all retries")


async def execute_stream_with_retry(
    stream_factory: Callable[[], AsyncGenerator[str, None]],
    *,
    max_retries: int = 3,
    timeout_seconds: float | None = None,
    operation_name: str = "LLM stream",
    retryable_exceptions: tuple = (ConnectionError, OSError),
) -> AsyncGenerator[str, None]:
    """
    Execute a streaming coroutine with retry logic and timeout on first chunk.

    Args:
        stream_factory: A callable that returns an async generator
        max_retries: Maximum number of retry attempts
        timeout_seconds: Timeout for first chunk (uses config.llm_timeout_seconds if None)
        operation_name: Name for logging purposes
        retryable_exceptions: Exception types that trigger a retry

    Yields:
        Chunks from the successful stream

    Raises:
        LLMTimeoutError: If first chunk times out on all attempts
        The last exception: If all retries are exhausted
    """
    if timeout_seconds is None:
        timeout_seconds = config.llm_timeout_seconds

    last_exception = None

    for attempt in range(max_retries):
        try:
            logger.debug("%s: attempt %d/%d", operation_name, attempt + 1, max_retries)

            # Get the async generator
            stream = stream_factory()

            # Get first chunk with timeout
            first_chunk = await asyncio.wait_for(stream.__anext__(), timeout=timeout_seconds)
            yield first_chunk

            # Yield remaining chunks without timeout (streaming)
            async for chunk in stream:
                yield chunk
            return

        except StopAsyncIteration:
            # Empty stream
            return

        except asyncio.TimeoutError:
            last_exception = LLMTimeoutError(
                f"{operation_name} timed out after {timeout_seconds}s "
                f"({max_retries} attempts)"
            )
            logger.error("%s timed out after %ss (attempt %d/%d)",
                         operation_name, timeout_seconds, attempt + 1, max_retries)

        except retryable_exceptions as e:
            last_exception = e
            wait_time = 2 ** attempt
            logger.warning(
                "%s error (attempt %d/%d): %s. Retrying in %ds...",
                operation_name, attempt + 1, max_retries, e, wait_time
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
                continue
            raise

        except Exception as e:
            # Non-retryable exception - re-raise immediately
            logger.error("%s failed with non-retryable error: %s", operation_name, e)
            raise

    # All retries exhausted
    if last_exception:
        raise last_exception
    raise RuntimeError(f"{operation_name} failed after all retries")
