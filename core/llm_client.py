"""
LLM Client abstraction layer for the Multi-Agent Automation Framework.

Provides a Protocol (interface) and a concrete Ollama implementation.
All agents receive an LLMClient via constructor injection instead of
importing `ollama` directly. This enables:
  - Swapping backends (vLLM, Groq, OpenAI) by writing one new class.
  - Unit testing with a FakeLLMClient that returns canned responses.
  - Centralizing keep_alive, num_ctx, and retry logic in one place.
"""
from collections.abc import AsyncGenerator
from typing import Any, Protocol, runtime_checkable

from core.circuit_breaker import CircuitBreaker
from core.llm_retry import execute_stream_with_retry, execute_with_retry
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
        format: str | None = None,
        images: list[str] | None = None,
        options: dict | None = None,
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

    async def stream_chat(
        self,
        model: str,
        messages: list[dict],
        format: str | None = None,
        images: list[str] | None = None,
        options: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Send a chat completion request and stream the response tokens.
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

    def __init__(self, num_ctx: int = 8192, keep_alive: int | str = "5m") -> None:
        self._num_ctx = num_ctx
        self._keep_alive = keep_alive

        # Instantiate AsyncClient once to reuse the aiohttp ClientSession
        from ollama import AsyncClient
        self._client = AsyncClient()
        self._breaker = CircuitBreaker(
            name="ollama",
            failure_threshold=3,
            recovery_timeout=60.0,
        )

    async def close(self) -> None:
        """Close the underlying aiohttp/httpx ClientSession to free resources."""
        if hasattr(self._client, 'close'):
            await self._client.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def chat(
        self,
        model: str,
        messages: list[dict],
        format: str | None = None,
        images: list[str] | None = None,
        options: dict | None = None,
    ) -> str:
        """Send a chat completion via the Ollama Async SDK with retry and timeout."""
        from core.config import config

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
        if images:
            kwargs["images"] = images

        async def _do_chat():
            async def _call():
                response = await self._client.chat(**kwargs)
                content = response.get("message", {}).get("content", "").strip()
                return str(content)

            return await execute_with_retry(
                _call,
                max_retries=3,
                timeout_seconds=config.llm_timeout_seconds,
                operation_name=f"Ollama chat (model={model})",
                retryable_exceptions=(ConnectionError, OSError),
            )

        return await self._breaker.call(_do_chat)

    async def stream_chat(
        self,
        model: str,
        messages: list[dict],
        format: str | None = None,
        images: list[str] | None = None,
        options: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        from core.config import config
        ollama_options = {"num_ctx": self._num_ctx}
        if options:
            ollama_options.update(options)

        kwargs: dict = {
            "model": model,
            "messages": messages,
            "options": ollama_options,
            "keep_alive": self._keep_alive,
            "stream": True
        }
        if format:
            kwargs["format"] = format
        if images:
            kwargs["images"] = images

        async def _stream_factory():
            response = await self._client.chat(**kwargs)
            async for chunk in response:
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content

        async for chunk in execute_stream_with_retry(
            _stream_factory,
            max_retries=3,
            timeout_seconds=config.llm_timeout_seconds,
            operation_name=f"Ollama stream (model={model})",
            retryable_exceptions=(ConnectionError, OSError),
        ):
            yield chunk


class LiteLLMClient:
    """
    Concrete LLMClient implementation wrapping litellm for cloud models (Claude, GPT, Gemini).
    """

    def __init__(self) -> None:
        self._breaker = CircuitBreaker(
            name="litellm",
            failure_threshold=3,
            recovery_timeout=60.0,
        )

    async def close(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def chat(
        self,
        model: str,
        messages: list[dict],
        format: str | None = None,
        images: list[str] | None = None,
        options: dict | None = None,
    ) -> str:
        import litellm

        from core.config import config

        # litellm expects messages in OpenAI format, which is the same as Ollama's
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        # If response_format is requested (e.g., json), map it for models that support it
        if format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        # Handle images for vision models (litellm supports OpenAI vision format)
        if images:
            # Convert to OpenAI vision format: add image_url to the last user message
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        msg["content"] = [
                            {"type": "text", "text": content},
                            *[{"type": "image_url", "image_url": {"url": img}} for img in images]
                        ]
                    break

        async def _do_chat():
            async def _call():
                # We need to map model names correctly if needed.
                # Claude 3.5 Sonnet -> "anthropic/claude-3-5-sonnet-20240620" or just "claude-3-5-sonnet-20240620"
                if model.startswith("claude-") and not model.startswith("anthropic/"):
                    api_model = f"anthropic/{model}"
                else:
                    api_model = model

                response = await litellm.acompletion(model=api_model, **kwargs)

                content = response.choices[0].message.content.strip()
                return str(content)

            return await execute_with_retry(
                _call,
                max_retries=3,
                timeout_seconds=config.llm_timeout_seconds,
                operation_name=f"LiteLLM chat (model={model})",
                retryable_exceptions=(Exception,),  # litellm can raise various exceptions
            )

        return await self._breaker.call(_do_chat)

    async def stream_chat(
        self,
        model: str,
        messages: list[dict],
        format: str | None = None,
        images: list[str] | None = None,
        options: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        import litellm

        from core.config import config

        # Handle images for vision models (litellm supports OpenAI vision format)
        if images:
            # Convert to OpenAI vision format: add image_url to the last user message
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        msg["content"] = [
                            {"type": "text", "text": content},
                            *[{"type": "image_url", "image_url": {"url": img}} for img in images]
                        ]
                    break

        kwargs = {
            "model": model if not (model.startswith("claude-") and not model.startswith("anthropic/")) else f"anthropic/{model}",
            "messages": messages,
            "stream": True
        }
        if format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        async def _stream_factory():
            # litellm.acompletion with stream=True returns an async generator
            response_gen = litellm.acompletion(**kwargs)

            # Get first chunk
            first_chunk = await response_gen.__anext__()
            content = first_chunk.choices[0].delta.content
            if content:
                yield content

            # Yield remaining chunks
            async for chunk in response_gen:
                content = chunk.choices[0].delta.content
                if content:
                    yield content

        async for chunk in execute_stream_with_retry(
            _stream_factory,
            max_retries=3,
            timeout_seconds=config.llm_timeout_seconds,
            operation_name=f"LiteLLM stream (model={model})",
            retryable_exceptions=(Exception,),
        ):
            yield chunk


class MultiLLMClient:
    """
    Routes requests to either Ollama or LiteLLM depending on the model name prefix.
    """

    def __init__(self, num_ctx: int = 8192, keep_alive: int | str = "5m") -> None:
        self.ollama = OllamaClient(num_ctx=num_ctx, keep_alive=keep_alive)
        self.litellm = LiteLLMClient()

    async def close(self) -> None:
        await self.ollama.close()
        await self.litellm.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _is_cloud_model(self, model: str) -> bool:
        # Common prefixes for cloud models
        cloud_prefixes = ["claude-", "gpt-", "gemini-", "anthropic/", "openai/", "google/", "nvidia/"]
        return any(model.startswith(prefix) for prefix in cloud_prefixes)

    def _is_vision_model(self, model: str) -> bool:
        """Check if model supports vision (image input)."""
        vision_models = [
            "gpt-4o", "gpt-4-turbo", "gpt-4-vision",
            "claude-3-5-sonnet", "claude-3-5-haiku", "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
            "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-pro", "gemini-2.5-flash",
            "llava", "llava-next", "bakllava", "moondream",
            "qwen2.5vl", "qwen2-vl",
            "pixtral", "nemotron-3-ultra",
        ]
        model_lower = model.lower()
        return any(vm in model_lower for vm in vision_models)

    async def chat(
        self,
        model: str,
        messages: list[dict],
        format: str | None = None,
        images: list[str] | None = None,
        options: dict | None = None,
    ) -> str:
        try:
            if self._is_cloud_model(model):
                return await self.litellm.chat(model, messages, format, images, options)
            else:
                return await self.ollama.chat(model, messages, format, images, options)
        except Exception as e:
            logger.warning(f"Primary LLM ({model}) failed: {e}. Attempting fallback routing.")
            fallback_model = "gemini/gemini-2.5-flash" if not self._is_cloud_model(model) else "qwen2.5-coder:14b"

            if self._is_cloud_model(fallback_model):
                return await self.litellm.chat(fallback_model, messages, format, images, options)
            else:
                return await self.ollama.chat(fallback_model, messages, format, images, options)

    async def stream_chat(
        self,
        model: str,
        messages: list[dict],
        format: str | None = None,
        images: list[str] | None = None,
        options: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        yielded_any = False
        try:
            if self._is_cloud_model(model):
                async for chunk in self.litellm.stream_chat(model, messages, format, images, options):
                    yielded_any = True
                    yield chunk
            else:
                async for chunk in self.ollama.stream_chat(model, messages, format, images, options):
                    yielded_any = True
                    yield chunk
        except Exception as e:
            if yielded_any:
                # Already yielded chunks - don't fall back, just re-raise
                logger.error(f"Primary LLM ({model}) failed after yielding chunks: {e}")
                raise
            logger.warning(f"Primary LLM ({model}) failed before first yield: {e}. Attempting fallback routing.")
            fallback_model = "gemini/gemini-2.5-flash" if not self._is_cloud_model(model) else "qwen2.5-coder:14b"

            if self._is_cloud_model(fallback_model):
                async for chunk in self.litellm.stream_chat(fallback_model, messages, format, images, options):
                    yield chunk
            else:
                async for chunk in self.ollama.stream_chat(fallback_model, messages, format, images, options):
                    yield chunk


class FakeLLMClient:
    """
    A test double that returns pre-configured responses.
    Use in unit tests to avoid requiring a running Ollama instance.

    Usage:
        fake = FakeLLMClient(responses=['["step 1"]', '{"approved": true}'])
        router = Router(llm=fake, model_name="test")
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or [])
        self._call_index = 0
        self.call_log: list[dict] = []

    async def chat(
        self,
        model: str,
        messages: list[dict],
        format: str | None = None,
        images: list[str] | None = None,
        options: dict | None = None,
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

    async def stream_chat(
        self,
        model: str,
        messages: list[dict],
        format: str | None = None,
        images: list[str] | None = None,
        options: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        # Just yield the canned response
        response = await self.chat(model, messages, format, images, options)
        for i in range(0, len(response), 5):
            yield response[i:i+5]
