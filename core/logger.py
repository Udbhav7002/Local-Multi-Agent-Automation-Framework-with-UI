"""
Logger module for standardized output across all framework components.
Uses rich for a clean, premium terminal look without emojis.
"""
import contextvars
import logging
import os
import re

from rich.console import Console
from rich.logging import RichHandler

# Correlation ID for tracking individual task executions
_task_id: contextvars.ContextVar[str] = contextvars.ContextVar('task_id', default='')
_request_ctx: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='')

def set_task_id(task_id: str) -> None:
    _task_id.set(task_id)
    _request_ctx.set(task_id)

def get_task_id() -> str:
    return _request_ctx.get() or _task_id.get()

# Share a single global console for the entire app
# Force terminal to False if in CI, otherwise auto-detect
console = Console(force_terminal=False if os.getenv("CI") else None)

class TaskIdFilter(logging.Filter):
    """Injects the task ID into log records."""
    def filter(self, record):
        record.task_id = get_task_id()
        return True

class PiiFilter(logging.Filter):
    PATTERNS = [
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL]'),
        (re.compile(r'(password|passwd|pwd|secret|key|token)\s*[:=]\s*\S+', re.I), r'\1=[REDACTED]'),
        (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), '[CREDIT_CARD]'),
    ]

    def filter(self, record):
        msg = str(record.getMessage())
        for pattern, replacement in self.PATTERNS:
            msg = pattern.sub(replacement, msg)
        record.msg = msg
        record.args = ()  # Clear formatting args to prevent re-interpolation
        return True

def setup_logger(name: str) -> logging.Logger:
    """Creates a configured logger with standard formatting."""
    logger = logging.getLogger(name)

    # Prevent adding handlers multiple times if instantiated multiple times
    if logger.hasHandlers():
        return logger

    debug_str = os.getenv("DEBUG", "False").strip().lower()
    logger.setLevel(logging.DEBUG if debug_str in ("true", "1", "t", "yes", "on") else logging.INFO)

    logger.addFilter(TaskIdFilter())
    logger.addFilter(PiiFilter())

    # Rich handler for clean, colorized terminal output
    handler = RichHandler(
        console=console,
        show_path=False,
        show_time=True,
        rich_tracebacks=True,
        markup=True
    )

    # We need a dynamic formatter because task_id can change
    class RichDynamicFormatter(logging.Formatter):
        def format(self, record):
            tid = getattr(record, 'task_id', '')
            if tid:
                # Add trace ID to message if present
                record.msg = f"[dim]{tid[:8]}[/dim] {record.msg}"
            return super().format(record)

    handler.setFormatter(RichDynamicFormatter("%(message)s"))
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
                    "task_id": get_task_id(),
                }
                if record.exc_info:
                    log_record["exception"] = self.formatException(record.exc_info)
                return json.dumps(log_record)

        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(os.path.join(log_dir, "framework.jsonl"))
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)

    if os.getenv("ENV") == "production":
        # Force JSON in production
        import json
        class ProdJsonFormatter(logging.Formatter):
            def format(self, record):
                log_record = {
                    "timestamp": self.formatTime(record, self.datefmt),
                    "name": record.name,
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "task_id": getattr(record, 'task_id', ''),
                }
                return json.dumps(log_record)
        handler.setFormatter(ProdJsonFormatter())

    return logger
