"""
LLM Client abstraction layer for the Multi-Agent Automation Framework.

Provides a Protocol (interface) and a concrete Ollama implementation.
All agents receive an LLMClient via constructor injection instead of
importing `ollama` directly. This enables:
  - Swapping backends (vLLM, Groq, OpenAI) by writing one new class.
  - Unit testing with a FakeLLMClient that returns canned responses.
  - Centralizing keep_alive, num_ctx, and retry logic in one place.
"""
from typing import Optional, Protocol, runtime_checkable

from core.logger import setup_logger

logger = setup_logger("LLMClient")


@runtime_checkable
class LLMClient(Protocol):
    """
    Abstract interface for LLM chat completion.
    All agents depend on this Protocol, never on a concrete SDK.
    """

    async def chat(
        self,
        model: str,
        messages: list[dict],
        format: Optional[str] = None,
        images: Optional[list[str]] = None,
        options: Optional[dict] = None,
    ) -> str:
        """
        Send a chat completion request and return the content string.

        Args:
            model: The model identifier (e.g., "qwen3-coder:30b").
            messages: The chat messages list.
            format: Optional output format hint (e.g., "json").
            images: Optional list of image paths for vision models.

        Returns:
            The raw content string from the model's response.
        """
        ...


class OllamaClient:
    """
    Concrete LLMClient implementation wrapping the Ollama Python SDK.

    Centralizes all Ollama-specific configuration:
    - keep_alive=0 for Zero-Concurrency GPU management
    - num_ctx for context window size
    - Uses AsyncClient for persistent HTTP connection pooling
    """

    def __init__(self, num_ctx: int = 8192, keep_alive: int = 0) -> None:
        self._num_ctx = num_ctx
        self._keep_alive = keep_alive
        
        # Instantiate AsyncClient once to reuse the aiohttp ClientSession
        from ollama import AsyncClient
        self._client = AsyncClient()

    async def chat(
        self,
        model: str,
        messages: list[dict],
        format: Optional[str] = None,
        images: Optional[list[str]] = None,
        options: Optional[dict] = None,
    ) -> str:
        """Send a chat completion via the Ollama Async SDK."""

        # Merge defaults with custom options if provided
        ollama_options = {"num_ctx": self._num_ctx}
        if options:
            ollama_options.update(options)

        kwargs: dict = {
            "model": model,
            "messages": messages,
            "options": ollama_options,
            "keep_alive": self._keep_alive,
        }
        if format:
            kwargs["format"] = format

        logger.debug("LLM request: model=%s, msgs=%d, format=%s",
                      model, len(messages), format)

        # Await the async client natively (no threads needed!)
        response = await self._client.chat(**kwargs)
        content = response.get("message", {}).get("content", "").strip()

        logger.debug("LLM response: %d chars", len(content))
        return content


class FakeLLMClient:
    """
    A test double that returns pre-configured responses.
    Use in unit tests to avoid requiring a running Ollama instance.

    Usage:
        fake = FakeLLMClient(responses=['["step 1"]', '{"approved": true}'])
        router = Router(llm=fake, model_name="test")
    """

    def __init__(self, responses: Optional[list[str]] = None) -> None:
        self._responses = list(responses or [])
        self._call_index = 0
        self.call_log: list[dict] = []

    async def chat(
        self,
        model: str,
        messages: list[dict],
        format: Optional[str] = None,
        images: Optional[list[str]] = None,
        options: Optional[dict] = None,
    ) -> str:
        """Return the next canned response, cycling if exhausted."""
        self.call_log.append({
            "model": model,
            "messages": messages,
            "format": format,
        })

        if not self._responses:
            return '{"intent": "task"}'

        response = self._responses[self._call_index % len(self._responses)]
        self._call_index += 1
        return response
