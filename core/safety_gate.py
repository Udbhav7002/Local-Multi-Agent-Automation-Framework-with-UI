"""
SafetyGate module for the Multi-Agent Automation Framework.
Encapsulates all dangerous-command detection and user approval logic.
"""
import asyncio
import shlex
from typing import Set

from core.logger import setup_logger

logger = setup_logger("SafetyGate")

class SafetyGate:
    """
    Strict Whitelist-based Safety Gate.
    Denies all commands by default unless explicitly whitelisted.
    """

    def __init__(self, llm=None, model_name: str = "", prompt_loader=None):
        self.llm = llm
        self.model_name = model_name
        self.prompt_loader = prompt_loader
        # Only these exact base binaries are allowed to run autonomously.
        # Keep this list highly restricted to read-only or harmless actions.
        self.allowed_base_commands: Set[str] = {
            "ls", "echo", "pwd", "whoami", "date", "cat", "git status",
            "dir", "systeminfo" # Added a few Windows equivalents 
        }

    def is_safe(self, command: str) -> bool:
        """
        Parses the command and checks if the base binary is whitelisted.
        """
        if not command or not command.strip():
            return False

        try:
            # shlex safely splits the command exactly like a Unix shell
            parts = shlex.split(command)
            if not parts:
                return False
            
            base_binary = parts[0].lower()
            
            # Identify chained commands or file redirections.
            # If the agent tries to pipe output or chain commands, force a manual review.
            unsafe_operators = ['&', '|', ';', '>', '<']
            if any(operator in command for operator in unsafe_operators):
                logger.debug("Command chaining detected. Forcing manual review.")
                return False

            return base_binary in self.allowed_base_commands

        except ValueError:
            # If shlex fails to parse it (e.g., due to unmatched quotes or malformed syntax),
            # default to denying the command.
            return False

    async def request_approval(self, command: str) -> bool:
        """
        Uses LLM intent scanner first. If not SAFE, prompts the user.
        Uses asyncio.to_thread to avoid blocking the main event loop.
        """
        logger.info(f"Scanning command with Intelligent Security Gate: {command}")
        if self.llm and self.prompt_loader:
            try:
                system_prompt = self.prompt_loader.load("safety", key="safety_prompt")
                content = await self.llm.chat(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Command: {command}"}
                    ],
                    format='json'
                )
                import json
                result = json.loads(content)
                if result.get("intent") == "SAFE":
                    logger.info(f"[bold green]LLM Security Gate Approved:[/bold green] {result.get('reason')}")
                    return True
                else:
                    logger.warning(f"[bold yellow]LLM Security Gate Denied/Warned:[/bold yellow] {result.get('reason')}")
            except Exception as e:
                logger.error(f"Intelligent Security Gate failed: {e}. Falling back to manual approval.")

        logger.warning(
            f"\n[bold red]⚠️ UNVERIFIED COMMAND INTERCEPTED[/bold red]\n"
            f"The agent is attempting to execute:\n"
            f"[bold cyan]{command}[/bold cyan]"
        )
        try:
            # Offload the blocking input() call to a separate thread
            ans = await asyncio.to_thread(
                input, "Allow execution? [y/N]: "
            )
            return ans.strip().lower() == 'y'
        except (EOFError, KeyboardInterrupt):
            logger.warning("Approval request interrupted. Denying command.")
            return False
