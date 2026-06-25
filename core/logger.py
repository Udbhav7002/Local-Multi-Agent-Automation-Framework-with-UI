"""
Logger module for standardized output across all framework components.
Uses rich for a clean, premium terminal look without emojis.
"""
import logging
import os

from rich.logging import RichHandler
from rich.console import Console

# Share a single global console for the entire app
# Force terminal to False if in CI, otherwise auto-detect
console = Console(force_terminal=False if os.getenv("CI") else None)

def setup_logger(name: str) -> logging.Logger:
    """Creates a configured logger with standard formatting."""
    logger = logging.getLogger(name)

    # Prevent adding handlers multiple times if instantiated multiple times
    if logger.hasHandlers():
        return logger

    debug_str = os.getenv("DEBUG", "False").strip().lower()
    logger.setLevel(logging.DEBUG if debug_str in ("true", "1", "t", "yes", "on") else logging.INFO)

    # Rich handler for clean, colorized terminal output
    handler = RichHandler(
        console=console,
        show_path=False,
        show_time=True,
        rich_tracebacks=True,
        markup=True
    )
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Optional: Structured JSON file logging (Phase 5/8)
    if os.getenv("ENABLE_JSON_LOGGING", "False").lower() in ("true", "1", "t"):
        import json
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_record = {
                    "timestamp": self.formatTime(record, self.datefmt),
                    "name": record.name,
                    "level": record.levelname,
                    "message": record.getMessage(),
                }
                if record.exc_info:
                    log_record["exception"] = self.formatException(record.exc_info)
                return json.dumps(log_record)

        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(log_dir, exist_ok=True)
            
        file_handler = logging.FileHandler(os.path.join(log_dir, "framework.jsonl"))
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)

    return logger
