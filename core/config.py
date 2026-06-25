"""
Configuration module for the Local Multi-Agent Automation Framework.
"""
import os
import json
import platform
from dataclasses import dataclass, field

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")

import logging
logger = logging.getLogger("Config")

def _get_env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            logger.warning(f"Invalid integer for {key}: '{val}'. Using default: {default}")
    return default

def _get_env_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is not None:
        try:
            return float(val)
        except ValueError:
            logger.warning(f"Invalid float for {key}: '{val}'. Using default: {default}")
    return default

@dataclass
class Config:
    """Central configuration for the framework."""
    # Models
    manager_model: str = os.getenv("MANAGER_MODEL", "llama3:latest")    # Planner model
    worker_model: str = os.getenv("WORKER_MODEL", "llama3:latest")      # Fast local model
    vision_model: str = os.getenv("VISION_MODEL", "llava:latest")

    # Retry logic
    max_plan_regenerations: int = _get_env_int("MAX_PLAN_REGENERATIONS", 3)
    max_step_retries: int = _get_env_int("MAX_STEP_RETRIES", 1)

    # Behavior
    auto_continue: bool = os.getenv(
        "AUTO_CONTINUE", "False").strip().lower() in (
        "true", "1", "yes", "y")

    # API endpoints
    ollama_base_url: str = os.getenv(
        "OLLAMA_BASE_URL", "http://localhost:11434")

    # Context window
    num_ctx: int = _get_env_int("NUM_CTX", 8192)

    # Memory settings
    memory_success_threshold: float = _get_env_float("MEMORY_SUCCESS_THRESHOLD", 0.15)
    memory_failure_threshold: float = _get_env_float("MEMORY_FAILURE_THRESHOLD", 0.2)
    memory_episode_threshold: float = _get_env_float("MEMORY_EPISODE_THRESHOLD", 0.25)

    # File paths
    screenshots_dir: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots"
    )

    # Execution limits
    cli_timeout_seconds: float = _get_env_float("CLI_TIMEOUT", 60.0)
    cli_max_output_chars: int = _get_env_int("CLI_MAX_OUTPUT", 2000)
    
    # Specific action timeouts (override cli_timeout_seconds if specified)
    action_timeouts: dict[str, float] = field(default_factory=lambda: {
        "run_command": _get_env_float("CLI_TIMEOUT", 60.0),
        "open_app": 10.0,
        "click": 15.0,
        "type": 15.0,
        "hotkey": 5.0,
        "sleep": 300.0, # allow up to 5 min sleep
        "goto": 30.0,
        "close_browser": 10.0
    })

    # LLM safety
    llm_timeout_seconds: float = _get_env_float("LLM_TIMEOUT", 120.0)
    max_prompt_chars: int = _get_env_int("MAX_PROMPT_CHARS", 24000)

    @property
    def os_context(self) -> str:
        """Auto-detect the OS and return a context string for agent prompts."""
        system = platform.system()  # 'Darwin', 'Linux', 'Windows'
        machine = platform.machine()  # 'arm64', 'x86_64', etc.

        if system == "Darwin":
            return (
                f"You are running on macOS ({machine}). "
                "Use macOS apps (Finder, Terminal, Safari, Notes, Preview) and macOS CLI tools "
                "(open, df, diskutil, pmset, say, pbcopy, osascript). "
                "NEVER use Windows apps (File Explorer, Command Prompt, PowerShell) or "
                "Windows commands (wmic, dir, ipconfig)."
            )
        elif system == "Linux":
            return (
                f"You are running on Linux ({machine}). "
                "Use Linux apps (Nautilus, gnome-terminal, Firefox) and Linux CLI tools "
                "(df, free, lsblk, xdg-open, xdotool). "
                "NEVER use Windows or macOS specific apps or commands."
            )
        elif system == "Windows":
            return (
                f"You are running on Windows ({machine}). "
                "Use Windows apps (File Explorer, Command Prompt, PowerShell, Notepad) and "
                "Windows CLI tools (wmic, dir, ipconfig, systeminfo). "
                "NEVER use macOS or Linux specific apps or commands."
            )
        else:
            return f"You are running on {system} ({machine})."

    def __post_init__(self):
        os.makedirs(self.screenshots_dir, exist_ok=True)
        max_allowed_ctx = _get_env_int("MAX_ALLOWED_CTX", 32768)
        if self.num_ctx > max_allowed_ctx:
            raise ValueError(f"Requested NUM_CTX ({self.num_ctx}) exceeds MAX_ALLOWED_CTX ({max_allowed_ctx}).")

        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "manager_model" in data:
                    self.manager_model = data["manager_model"]
                if "worker_model" in data:
                    self.worker_model = data["worker_model"]
                if "vision_model" in data:
                    self.vision_model = data["vision_model"]
                if "num_ctx" in data:
                    self.num_ctx = data["num_ctx"]
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "manager_model": self.manager_model,
                    "worker_model": self.worker_model,
                    "vision_model": self.vision_model,
                    "num_ctx": self.num_ctx
                }, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

config = Config()
