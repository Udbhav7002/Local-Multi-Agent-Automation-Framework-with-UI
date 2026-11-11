"""
Configuration module for the Local Multi-Agent Automation Framework.
"""
# Configuration Precedence (highest to lowest):
# 1. settings.json (runtime-persisted via Config.save())
# 2. Environment variables (or .env file)
# 3. Pydantic Defaults below
import json
import logging
import os
import platform
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("Config")

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")

class Config(BaseSettings):
    """Central configuration for the framework."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Models
    manager_model: str = "qwen3-coder:30b"
    worker_model: str = "qwen2.5-coder:14b"
    vision_model: str = "qwen2.5vl:7b"
    critic_model: str = "llama3.2:3b"

    # Retry logic
    max_plan_regenerations: int = 3
    max_step_retries: int = 1

    # Behavior
    auto_continue: bool = False

    # Vision verification
    vision_auto_continue_on_uncertain: bool = False

    # Cloud Vision & Cost Controls
    cloud_vision_enabled: bool = False
    cloud_vision_consent_given: bool = False
    max_vision_cost_per_session_usd: float = 1.0
    max_vision_cost_per_request_usd: float = 0.10

    # API endpoints
    ollama_base_url: str = "http://localhost:11434"

    # Context window
    num_ctx: int = 8192

    # Memory settings
    memory_success_threshold: float = 0.15
    memory_failure_threshold: float = 0.2
    memory_episode_threshold: float = 0.25

    # File paths
    screenshots_dir: str = Field(
        default_factory=lambda: os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots"
        )
    )
    screenshot_retention_days: int = 7

    # Execution limits
    cli_timeout_seconds: float = 60.0
    cli_max_output_chars: int = 2000

    action_timeouts: dict[str, float] = Field(default_factory=lambda: {
        "run_command": 60.0,
        "open_app": 10.0,
        "click": 15.0,
        "type": 15.0,
        "hotkey": 5.0,
        "sleep": 300.0,
        "goto": 30.0,
        "close_browser": 10.0
    })

    # LLM safety
    llm_timeout_seconds: float = 120.0
    max_prompt_chars: int = 24000

    # Sandbox
    sandbox_root: str = ""

    @property
    def os_context(self) -> str:
        """Auto-detect the OS and return a context string for agent prompts."""
        system = platform.system()  # 'Darwin', 'Linux', 'Windows'
        machine = platform.machine()  # 'arm64', 'x86_64', etc.

        contexts = {
            "Darwin": (
                f"You are running on macOS ({machine}). "
                "Use macOS apps (Finder, Terminal, Safari, Notes, Preview) and macOS CLI tools "
                "(open, df, diskutil, pmset, say, pbcopy, osascript). "
                "NEVER use Windows apps (File Explorer, Command Prompt, PowerShell) or "
                "Windows commands (wmic, dir, ipconfig)."
            ),
            "Linux": (
                f"You are running on Linux ({machine}). "
                "Use Linux apps (Nautilus, gnome-terminal, Firefox) and Linux CLI tools "
                "(df, free, lsblk, xdg-open, xdotool). "
                "NEVER use Windows or macOS specific apps or commands."
            ),
            "Windows": (
                f"You are running on Windows ({machine}). "
                "Use Windows apps (File Explorer, Command Prompt, PowerShell, Notepad) and "
                "Windows CLI tools (wmic, dir, ipconfig, systeminfo). "
                "NEVER use macOS or Linux specific apps or commands."
            ),
        }
        if system in contexts:
            return contexts[system]
        return f"You are running on {system} ({machine})."

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        os.makedirs(self.screenshots_dir, exist_ok=True)

        # Load from settings.json (highest precedence for runtime overrides)
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    if hasattr(self, k):
                        setattr(self, k, v)
            except Exception as e:
                logger.warning(f"Error loading settings.json: {e}")

        # Validate num_ctx after all overrides are applied
        max_allowed_ctx = int(os.getenv("MAX_ALLOWED_CTX", 32768))
        if self.num_ctx > max_allowed_ctx:
            raise ValueError(f"Requested NUM_CTX ({self.num_ctx}) exceeds MAX_ALLOWED_CTX ({max_allowed_ctx}).")

    def save(self) -> None:
        """Persist all runtime-configurable settings to disk."""
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "manager_model": self.manager_model,
                    "worker_model": self.worker_model,
                    "vision_model": self.vision_model,
                    "critic_model": self.critic_model,
                    "num_ctx": self.num_ctx,
                    "max_plan_regenerations": self.max_plan_regenerations,
                    "max_step_retries": self.max_step_retries,
                    "cli_timeout_seconds": self.cli_timeout_seconds,
                    "cli_max_output_chars": self.cli_max_output_chars,
                    "llm_timeout_seconds": self.llm_timeout_seconds,
                    "max_prompt_chars": self.max_prompt_chars,
                    "memory_success_threshold": self.memory_success_threshold,
                    "memory_failure_threshold": self.memory_failure_threshold,
                    "memory_episode_threshold": self.memory_episode_threshold,
                    "screenshot_retention_days": self.screenshot_retention_days,
                    "auto_continue": self.auto_continue,
                    "vision_auto_continue_on_uncertain": self.vision_auto_continue_on_uncertain,
                    "cloud_vision_enabled": self.cloud_vision_enabled,
                    "cloud_vision_consent_given": self.cloud_vision_consent_given,
                    "max_vision_cost_per_session_usd": self.max_vision_cost_per_session_usd,
                    "max_vision_cost_per_request_usd": self.max_vision_cost_per_request_usd,
                    "ollama_base_url": self.ollama_base_url,
                    "action_timeouts": self.action_timeouts,
                    "sandbox_root": self.sandbox_root,
                }, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")

config = Config()
