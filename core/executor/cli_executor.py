"""
CLI execution strategy — runs shell commands via asyncio subprocess.
"""
# pylint: disable=broad-exception-caught
import asyncio
import contextlib
import os
import signal

from core.config import config
from core.logger import setup_logger

SHELL_METACHARACTERS = {'|', ';', '&&', '||', '`', '$(', '>', '>>', '<', '<<'}

logger = setup_logger("CLIExecutor")


class CLIExecutor:
    """Executes native shell commands with timeout and output truncation."""

    async def execute(self, action: str, target: str) -> tuple[bool, str]:
        """Execute a CLI command."""
        return await self._run_command(target)

    async def _run_command(self, command: str) -> tuple[bool, str]:
        """Executes a native command via shell on macOS."""
        if not command.strip():
            return False, "Empty command"

        try:
            logger.debug("Running CLI command via shell: %s", command)
            # Use start_new_session=True to create a new process group
            # so we can kill the entire group on timeout (including child processes)
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=config.cli_timeout_seconds
                )
            except asyncio.TimeoutError:
                # Kill the entire process group to avoid orphaned child processes
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
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
