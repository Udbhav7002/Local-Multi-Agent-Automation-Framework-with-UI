"""
Vision verification module for evaluating screen states using a vision-language model.
"""
import asyncio
import json
import re

from core.config import config
from core.cost_tracker import get_cost_tracker
from core.logger import setup_logger
from vision.screen_capture import ScreenCapture

logger = setup_logger("VisionVerifier")


class VisionVerifier:  # pylint: disable=too-few-public-methods
    """
    Uses a vision-language model to determine if a goal was achieved
    on the current screen.
    """
    def __init__(self, llm, model_name: str = "llava", ui_parser=None) -> None:
        self.llm = llm
        self.model_name = model_name
        self.screen_cap = ScreenCapture()
        self.ui_parser = ui_parser
        self._cost_tracker = get_cost_tracker()
        # Check if the LLM client is a MultiLLMClient to detect cloud models
        self._is_cloud = self._detect_cloud_model()

    def _detect_cloud_model(self) -> bool:
        """Detect if the current model routes through cloud provider."""
        if hasattr(self.llm, '_is_cloud_model'):
            return bool(self.llm._is_cloud_model(self.model_name))
        if hasattr(self.llm, 'ollama') and hasattr(self.llm, 'litellm'):
            # MultiLLMClient
            return bool(self.llm._is_cloud_model(self.model_name))
        return False

    def _build_vision_message(self, prompt: str, screenshot_path: str) -> dict:
        """Build message with image in the correct format for the model."""
        if self._is_cloud:
            # OpenAI-compatible format (LiteLLM)
            return {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {'url': screenshot_path}}
                ]
            }
        else:
            # Ollama format
            return {
                'role': 'user',
                'content': prompt,
                'images': [screenshot_path]
            }

    def _estimate_tokens(self, prompt: str, has_image: bool = True) -> tuple[int, int]:
        """Rough token estimation for vision requests."""
        # Rough estimate: ~4 chars per token for text
        text_tokens = len(prompt) // 4
        # Image tokens: ~85 tokens per tile for GPT-4o (low detail),
        # up to ~170 for high detail. We'll estimate 200 for safety.
        image_tokens = 200 if has_image else 0
        # Output estimate: JSON response ~50 tokens
        output_tokens = 50
        return text_tokens + image_tokens, output_tokens

    def _check_cloud_permissions(self) -> tuple[bool, str]:
        """Check if cloud vision is enabled and user has consented."""
        if not self._is_cloud:
            return True, ""
        if not config.cloud_vision_enabled:
            return False, "Cloud vision is disabled. Set cloud_vision_enabled=true in config to enable."
        if not config.cloud_vision_consent_given:
            return False, "Cloud vision requires explicit consent. Set cloud_vision_consent_given=true after reviewing privacy implications."
        return True, ""

    def _check_budget(self, prompt: str) -> tuple[bool, str]:
        """Check if request fits within budget limits."""
        if not self._is_cloud:
            return True, ""
        input_tokens, output_tokens = self._estimate_tokens(prompt)
        can_afford, reason = self._cost_tracker.can_afford_request(
            self.model_name, input_tokens, output_tokens)
        return can_afford, reason

    def _record_usage(self, prompt: str, operation: str) -> None:
        """Record actual token usage after a request."""
        if not self._is_cloud:
            return
        input_tokens, output_tokens = self._estimate_tokens(prompt)
        self._cost_tracker.record_usage(
            self.model_name, input_tokens, output_tokens, operation)

    def _fast_ocr_verify(self, image_path: str, expected_outcome: str, target_text: str, action: str) -> tuple[bool, str]:
        """
        Fast-path verification using OCR instead of the slow VLM.
        """
        if not self.ui_parser:
            return False, ""

        extracted_text = self.ui_parser.extract_all_text(image_path).lower()
        if not extracted_text:
            return False, ""

        # 1. For 'type' actions, the typed text should be visible on screen
        if action == "type" and len(target_text) > 2 and target_text.lower() in extracted_text:
            logger.info("OCR Fast-Path: Found typed text '%s' on screen.", target_text)
            return True, f"OCR verified typed text: '{target_text}' is visible on screen."

        # 2. Look for any quoted strings in the expected outcome
        quotes = re.findall(r"'([^']*)'", expected_outcome) + re.findall(r'"([^"]*)"', expected_outcome)
        for q in quotes:
            if len(q) > 2 and q.lower() in extracted_text:
                logger.info("OCR Fast-Path: Found expected quote '%s' on screen.", q)
                return True, f"OCR verified expected text: '{q}' is visible on screen."

        return False, "OCR check inconclusive."

    async def verify(self, expected_outcome: str, target_text: str = "", action: str = "") -> tuple[bool, str]:
        """
        Takes a screenshot and asks the model if the outcome was achieved.
        """
        logger.info("Capturing screen to verify: '%s'...", expected_outcome)
        screenshot_path = await asyncio.to_thread(
            self.screen_cap.capture_fullscreen, "current_state.png")

        # FAST PATH: Instant OCR Verification
        ocr_success, ocr_msg = await asyncio.to_thread(
            self._fast_ocr_verify, screenshot_path, expected_outcome, target_text, action)
        if ocr_success:
            return True, ocr_msg

        # Check cloud permissions
        allowed, reason = self._check_cloud_permissions()
        if not allowed:
            logger.warning("Cloud vision blocked: %s", reason)
            return False, reason

        prompt = (
            f"Look at this screenshot. Is the current state of the screen consistent with this goal: '{expected_outcome}'?\n"
            "CRITICAL RULES:\n"
            "1. Be extremely lenient. If the screen shows the desired end-state (e.g. the correct page is loaded), output success: true. Do NOT fail it just because the action to get there is already finished.\n"
            "2. Do NOT be pedantic about how the goal was achieved. If the user asked to 'open Brave' and you see a browser open, that's success.\n"
            "You must reply with a valid JSON object exactly like this: "
            "{{\"success\": true, \"reason\": \"your reason here\"}}"
        )

        # Check budget
        allowed, reason = self._check_budget(prompt)
        if not allowed:
            logger.warning("Budget exceeded: %s", reason)
            return False, f"Budget limit: {reason}"

        try:
            logger.debug("Asking %s to verify...", self.model_name)
            message = self._build_vision_message(prompt, screenshot_path)
            answer = await self.llm.chat(
                model=self.model_name,
                messages=[message],
                format='json',
                options={'temperature': 0.0}
            )

            # Record usage
            self._record_usage(prompt, "vision_verify")

            # Clean up markdown code blocks if present
            clean_answer = answer.replace(
                "```json", "").replace(
                "```", "").strip()

            try:
                # Try to parse the cleaned string directly
                result = json.loads(clean_answer)
                is_success = result.get('success', False)
                reason = result.get('reason', 'No reason provided')
                logger.info(
                    "Verifier response: %s (Success: %s)", reason, is_success)
                return is_success, reason
            except json.JSONDecodeError:
                # Fallback: Extract via regex if JSON is malformed
                success_match = re.search(
                    r'"success"\s*:\s*(true|false)', answer, re.IGNORECASE)
                reason_match = re.search(
                    r'"reason"\s*:\s*"([^"]+)"', answer, re.IGNORECASE)

                if success_match:
                    is_success = success_match.group(1).lower() == 'true'
                    reason = reason_match.group(
                        1) if reason_match else 'Failed to parse reason.'
                    logger.warning(
                        "Verifier response (Regex Fallback): %s (Success: %s)",
                        reason, is_success)
                    return is_success, reason

            # Ultimate Fallback
            logger.error("Verifier returned invalid format: %s", answer)
            return False, f"Invalid vision format: {answer}"

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Vision Verification Error: %s", e)
            return False, f"Vision Error: {e}"

    async def ask(self, question: str) -> str:
        """
        Takes a screenshot and asks the vision model an arbitrary question.
        """
        logger.info("Capturing screen to answer question...")
        screenshot_path = await asyncio.to_thread(
            self.screen_cap.capture_fullscreen, "question_state.png")

        # Check cloud permissions
        allowed, reason = self._check_cloud_permissions()
        if not allowed:
            logger.warning("Cloud vision blocked: %s", reason)
            return f"Cloud vision blocked: {reason}"

        prompt = (
            f"You are an AI assistant looking at the user's screen. "
            f"Answer the following question about what you see: {question}"
        )

        # Check budget
        allowed, reason = self._check_budget(prompt)
        if not allowed:
            logger.warning("Budget exceeded: %s", reason)
            return f"Budget limit: {reason}"

        try:
            message = self._build_vision_message(prompt, screenshot_path)
            content = await self.llm.chat(
                model=self.model_name,
                messages=[message],
                options={'temperature': 0.0}
            )

            # Record usage
            self._record_usage(prompt, "vision_ask")
            return str(content.strip())
        except Exception as e:
            logger.error("Vision Question Error: %s", e)
            return f"I ran into an error trying to see the screen: {e}"

    def get_cost_summary(self) -> dict:
        """Get current session cost summary."""
        return self._cost_tracker.get_session_summary()
