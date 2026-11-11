"""
Response parser utility for cleaning and extracting structured JSON
from LLM outputs. Centralizes all the defensive parsing logic that
was previously duplicated across Planner and Worker.
"""
import json
import re

from core.logger import setup_logger

logger = setup_logger("ResponseParser")


class ResponseParser:
    """
    Cleans raw LLM output and extracts valid JSON.
    Handles common LLM quirks: <think> blocks, markdown fences,
    trailing commas, and embedded prose around JSON.
    """

    REQUIRED_STEP_KEYS = {"action", "target", "method"}

    @staticmethod
    def clean_and_extract_json(
            raw: str, shape: str = "array") -> str:
        """
        Takes raw LLM output and returns a clean JSON string.

        Args:
            raw: The raw string from the LLM response.
            shape: "array" to extract [...], "object" to extract {...}.

        Returns:
            A validated JSON string.

        Raises:
            ValueError: If no valid JSON can be extracted.
        """
        content = raw.strip()

        # 1. Strip <think>...</think> blocks (reasoning models like DeepSeek-R1, Qwen3)
        content = re.sub(
            r'<think>.*?</think>', '', content, flags=re.DOTALL
        ).strip()

        # 2. Strip markdown code fences (```json ... ```)
        content = re.sub(
            r'```(?:json)?\s*\n?', '', content
        ).strip()

        # 3. Extract the target JSON shape using reliable find/rfind
        if shape == "array":
            start_idx = content.find('[')
            end_idx = content.rfind(']')
            if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                content = content[start_idx:end_idx+1]
        elif shape == "object":
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                content = content[start_idx:end_idx+1]
        else:
            raise ValueError(f"Unknown shape: {shape}. Use 'array' or 'object'.")

        # 4. Remove trailing commas (common LLM hallucination)
        content = re.sub(r',\s*([\]}])', r'\1', content)

        # 5. Validate that it's actually parseable JSON
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to extract valid JSON (shape=%s): %s\nRaw content: %s",
                shape, e, raw[:500]
            )
            raise ValueError(
                f"Could not extract valid JSON ({shape}): {e}"
            ) from e

        return content.strip()

    @staticmethod
    def validate_action_step(step: dict, step_index: int = 0) -> dict:
        """
        Validates that a Worker action step dict has all required keys.
        Raises ValueError if the step is malformed.
        """
        if not isinstance(step, dict):
            raise ValueError(
                f"Worker step {step_index} is not a dict: {type(step).__name__}"
            )

        missing = ResponseParser.REQUIRED_STEP_KEYS - set(step.keys())
        if missing:
            raise ValueError(
                f"Worker step {step_index} missing required keys: {missing}. "
                f"Got: {step}"
            )

        # Validate types
        for key in ('action', 'target', 'method'):
            if not isinstance(step.get(key), str):
                raise ValueError(
                    f"Worker step {step_index} key '{key}' must be a string, "
                    f"got {type(step.get(key)).__name__}"
                )

        return step

    @staticmethod
    def parse_worker_output(raw_json: str) -> list:
        """
        Parses Worker JSON output into a validated list of action step dicts.
        Handles the common case where the Worker returns a single
        dict instead of a list.
        """
        data = json.loads(raw_json)

        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError(
                f"Expected list or dict from Worker, got {type(data).__name__}"
            )

        # Validate each step
        validated = []
        for i, step in enumerate(data):
            validated.append(ResponseParser.validate_action_step(step, i))

        return validated
