"""
Base protocol for all executor strategies.
"""
from typing import Protocol, Tuple


class BaseExecutor(Protocol):
    """
    Protocol that every execution strategy must implement.
    Each strategy handles one execution method (CLI, GUI, Browser, System).
    """

    async def execute(self, action: str, target: str) -> Tuple[bool, str]:
        """
        Execute a single action.

        Args:
            action: The action verb (e.g. "run_command", "click", "goto").
            target: The target/argument for the action.

        Returns:
            A tuple of (success, output_message).
        """
        ...
