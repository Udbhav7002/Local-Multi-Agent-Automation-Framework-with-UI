"""
Base protocol for all executor strategies.
"""
from typing import Protocol


class BaseExecutor(Protocol):
    """
    Protocol that every execution strategy must implement.
    Each strategy handles one execution method (CLI, GUI, Browser, System).
    """

    async def execute(self, action: str, target: str) -> tuple[bool, str]:
        """
        Execute a single action.

        Args:
            action: The action verb (e.g. "run_command", "click", "goto").
            target: The target/argument for the action.

        Returns:
            A tuple of (success, output_message).
        """
        ...

class PluginExecutor(Protocol):
    """
    Protocol for executor plugins placed in the plugins/ directory.

    Plugins must define:
    - PLUGIN_NAME: str — Human-readable name for logging
    - ACTIONS: list[str] — Action names this plugin handles
    - execute(action, target) — Execute the action

    Optional:
    - shutdown() — Called during framework shutdown for cleanup
    """
    PLUGIN_NAME: str
    ACTIONS: list[str]

    async def execute(self, action: str, target: str) -> tuple[bool, str]:
        ...
