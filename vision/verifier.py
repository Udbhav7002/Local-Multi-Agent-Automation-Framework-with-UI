"""
Vision verification module for evaluating screen states using a vision-language model.
"""
import json
import re

from core.logger import setup_logger
from core.config import config
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
        if action == "type" and len(target_text) > 2:
            if target_text.lower() in extracted_text:
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
        screenshot_path = self.screen_cap.capture_fullscreen(
            "current_state.png")

        # FAST PATH: Instant OCR Verification
        ocr_success, ocr_msg = self._fast_ocr_verify(screenshot_path, expected_outcome, target_text, action)
        if ocr_success:
            return True, ocr_msg


        prompt = (
            f"Look at this screenshot. Is the current state of the screen consistent with this goal: '{expected_outcome}'?\n"
            "CRITICAL RULES:\n"
            "1. Be extremely lenient. If the screen shows the desired end-state (e.g. the correct page is loaded), output success: true. Do NOT fail it just because the action to get there is already finished.\n"
            "2. Do NOT be pedantic about how the goal was achieved. If the user asked to 'open Brave' and you see a browser open, that's success.\n"
            "You must reply with a valid JSON object exactly like this: "
            "{{\"success\": true, \"reason\": \"your reason here\"}}"
        )

        try:
            logger.debug("Asking %s to verify...", self.model_name)
            # Images are passed in the message dict for ollama compatibility
            answer = await self.llm.chat(
                model=self.model_name,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [screenshot_path]
                }],
                format='json',
                options={'temperature': 0.0}
            )

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
        screenshot_path = self.screen_cap.capture_fullscreen("question_state.png")

        prompt = (
            f"You are an AI assistant looking at the user's screen. "
            f"Answer the following question about what you see: {question}"
        )
        
        try:
            # We assume OllamaClient handles passing images to vision models.
            # In our current setup, images are passed in the 'images' key of the message.
            messages = [{
                'role': 'user', 
                'content': prompt, 
                'images': [screenshot_path]
            }]
            
            content = await self.llm.chat(
                model=self.model_name,
                messages=messages,
                options={'temperature': 0.0}
            )
            return content.strip()
        except Exception as e:
            logger.error("Vision Question Error: %s", e)
            return f"I ran into an error trying to see the screen: {e}"
