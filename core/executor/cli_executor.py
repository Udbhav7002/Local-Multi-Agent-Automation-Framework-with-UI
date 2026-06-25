"""
CLI execution strategy — runs shell commands via asyncio subprocess.
"""
# pylint: disable=broad-exception-caught
import asyncio
from typing import Tuple

from core.config import config
from core.logger import setup_logger

logger = setup_logger("CLIExecutor")


class CLIExecutor:
    """Executes native shell commands with timeout and output truncation."""

    async def execute(self, action: str, target: str) -> Tuple[bool, str]:
        """Execute a CLI command."""
        return await self._run_command(target)

    async def _run_command(self, command: str) -> Tuple[bool, str]:
        """Executes a native command via subprocess on macOS."""
        try:
            logger.debug("Running CLI command: %s", command)
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=config.cli_timeout_seconds
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                logger.error(
                    "CLI command timed out after %s seconds: %s",
                    config.cli_timeout_seconds, command
                )
                return False, (
                    f"Command failed: Timed out after "
                    f"{int(config.cli_timeout_seconds)} seconds."
                )

            output = stdout.decode().strip()
            error_output = stderr.decode().strip()

            # Truncate extremely long outputs to prevent model context blowout
            max_out = config.cli_max_output_chars
            if len(output) > max_out:
                output = output[:max_out] + "\n... [truncated]"
            if len(error_output) > max_out:
                error_output = error_output[:max_out] + "\n... [truncated]"

            if process.returncode == 0:
                logger.debug("CLI command succeeded: %s", output)
                return True, output if output else "Command executed successfully with no output."

            logger.error("CLI command failed (%s): %s", process.returncode, error_output)
            return False, f"Command failed with code {process.returncode}: {error_output}"

        except Exception as e:
            logger.error("Failed to launch subprocess: %s", e)
            return False, f"Failed to launch subprocess: {str(e)}"
