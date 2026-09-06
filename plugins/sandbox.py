"""
SandboxExecutor — runs unsafe terminal commands in an ephemeral Docker container.
"""
import asyncio
from typing import Tuple

from core.logger import setup_logger
from core.config import config

logger = setup_logger("SandboxExecutor")

class SandboxExecutor:
    """
    Executes terminal commands inside a fresh, isolated Docker container.
    Hardened with: no network, read-only rootfs, resource limits, no new privileges.
    """
    PLUGIN_NAME = "SandboxExecutor"
    ACTIONS = ["run_sandbox_command"]
    
    def __init__(self, image: str = "ubuntu:latest"):
        self.image = image

    async def execute(self, action: str, target: str) -> Tuple[bool, str]:
        """
        Executes the target command in a hardened Docker container.
        """
        if action not in self.ACTIONS:
            return False, f"SandboxExecutor only supports 'run_sandbox_command', got '{action}'"
            
        logger.info("[bold yellow]Executing command in Docker Sandbox: %s[/bold yellow]", target)
        
        # Hardened docker run: no network, read-only rootfs, resource limits, no new privileges
        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:noexec,nosuid,size=100m",
            "--cpus", "1.0",
            "--memory", "512m",
            "--pids-limit", "100",
            "--security-opt", "no-new-privileges",
            "--user", "nobody:nogroup",
            self.image,
            "bash", "-c", target
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Apply timeout from config
            timeout = config.action_timeouts.get("run_sandbox_command", config.cli_timeout_seconds)
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return False, f"Sandbox command timed out after {timeout} seconds"
            
            output = ""
            if stdout:
                output += stdout.decode().strip()
            if stderr:
                output += "\n" + stderr.decode().strip()
                
            success = process.returncode == 0
            
            if success:
                logger.debug("Sandbox command succeeded.")
            else:
                logger.warning("Sandbox command failed with exit code %s", process.returncode)
                
            return success, output.strip()
            
        except FileNotFoundError:
            msg = "Docker is not installed or not in PATH. Cannot run sandboxed command."
            logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"Error executing sandboxed command: {e}"
            logger.error(msg)
            return False, msg
