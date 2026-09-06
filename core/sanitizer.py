"""
Input Sanitizer module to defend against prompt injection and jailbreaks.
"""
import re
from core.logger import setup_logger

logger = setup_logger("InputSanitizer")

class PromptInjectionError(ValueError):
    """Raised when malicious input is detected."""
    pass

class InputSanitizer:
    """
    Sanitizes user input before routing to prevent prompt injections.
    """
    def __init__(self):
        # Common patterns used to break out of system prompts
        self.jailbreak_patterns = [
            r"(?i)ignore\s+(all\s+)?(previous\s+)?(instructions|directions)",
            r"(?i)disregard\s+(all\s+)?(previous\s+)?(instructions|directions)",
            r"(?i)you\s+are\s+now",
            r"(?i)new\s+system\s+prompt",
            r"(?i)new\s+role",
            r"(?i)forget\s+what\s+I\s+told\s+you",
            r"(?i)forget\s+your\s+previous",
        ]
        
        # Detect delimiter overloads (e.g., trying to close a prompt boundary)
        self.delimiter_patterns = [
            r"\[/SYSTEM\]",
            r"\[/INST\]",
            r"```json",  # Suspicious if at the very beginning of input
            r"###",      # Overuse of markdown headers used in prompts
            r"<<<",
            r">>>",
        ]

    def sanitize(self, user_input: str) -> str:
        """
        Inspects the input for malicious patterns.
        Raises PromptInjectionError if a hard block is matched.
        Otherwise returns the trimmed string.
        """
        cleaned = user_input.strip()
        if not cleaned:
            return cleaned

        # 1. Check for jailbreak phrases
        for pattern in self.jailbreak_patterns:
            if re.search(pattern, cleaned):
                logger.warning(f"[red]Prompt Injection Detected (Jailbreak):[/red] Match on '{pattern}'")
                raise PromptInjectionError("Input rejected due to suspected prompt injection.")

        # 2. Check for delimiter overload (heuristics)
        for pattern in self.delimiter_patterns:
            if re.search(pattern, cleaned, re.IGNORECASE):
                logger.warning(f"[yellow]Suspicious Delimiter Detected:[/yellow] Match on '{pattern}'")
                # We could reject or strip. Let's reject to be safe.
                raise PromptInjectionError("Input contains restricted structural delimiters.")

        # 3. Limit input size to prevent DoS via massive token contexts
        MAX_INPUT_LENGTH = 10000
        if len(cleaned) > MAX_INPUT_LENGTH:
            logger.warning(f"Input truncated from {len(cleaned)} to {MAX_INPUT_LENGTH} characters.")
            cleaned = cleaned[:MAX_INPUT_LENGTH]

        return cleaned
