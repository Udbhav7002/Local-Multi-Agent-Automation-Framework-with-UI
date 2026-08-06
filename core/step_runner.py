"""
StepRunner module for the Multi-Agent Automation Framework.
Extracts the step execution, retry, and vision verification loop
from the Orchestrator into a focused, testable class.
"""
import asyncio
import json
from collections import deque
from typing import Tuple

from core.config import config
from core.logger import setup_logger
from core.models import ActionStep
from core.response_parser import ResponseParser
from core.safety_gate import SafetyGate
from core.events import StepExecutedEvent, EventBus

logger = setup_logger("StepRunner")

# Maximum characters to keep in the action history sliding window
_MAX_HISTORY_CHARS = 1500


class StepRunner:
    """
    Executes a list of high-level sub-tasks by delegating to the Worker
    and Executor, with retry logic, vision verification, and safety gates.
    
    TODO: Decouple this class to avoid heavy reliance on hasattr/value checks.
    """

    @staticmethod
    def _enum_val(obj) -> str:
        """Extract string value from enum or pass through string."""
        return obj.value if hasattr(obj, 'value') else str(obj)

    def __init__(
        self,
        worker,
        executor,
        verifier,
        safety_gate: SafetyGate | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.worker = worker
        self.executor = executor
        self.verifier = verifier
        self.safety_gate = safety_gate or SafetyGate()
        self.event_bus = event_bus
        self.undo_stack: list[ActionStep] = []
        self._cancelled = False

    def cancel(self) -> None:
        """Signal that all in-flight steps should stop."""
        self._cancelled = True
        logger.info("[yellow]StepRunner received cancellation signal.[/yellow]")

    async def run(self, steps: list[str]) -> Tuple[bool, str, list[dict]]:
        """
        Executes a list of high-level sub-tasks via the Worker Agent.
        Returns (success: bool, failure_feedback: str, steps_executed: list[dict]).
        """
        # Use a deque as a sliding window to prevent context blowout
        action_history: deque = deque(maxlen=20)
        steps_executed: list[dict] = []

        for i, sub_task in enumerate(steps):
            if self._cancelled:
                logger.warning("Execution cancelled by user.")
                return False, "Execution cancelled.", steps_executed

            logger.info(
                "Manager delegating sub-task %s to Worker: '%s'",
                i + 1, sub_task
            )

            # Build the history string from the sliding window
            history_str = "\n".join(action_history)

            try:
                worker_json = await self.worker.generate_action(
                    sub_task, history_str
                )
                worker_steps = ResponseParser.parse_worker_output(worker_json)
            except (ValueError, KeyError) as e:
                import json
                logger.error("Worker failed to break down task: %s", e)
                return False, (
                    f"Worker Agent failed to generate actions for "
                    f"sub-task '{sub_task}': {e}"
                ), steps_executed

            for j, raw_step in enumerate(worker_steps):
                step = ActionStep.from_dict(raw_step)

                step_success, feedback, duration_ms = await self._execute_single_step(
                    step, i, j, action_history
                )
                
                steps_executed.append({
                    "action": self._enum_val(step.action),
                    "target": step.target,
                    "success": step_success,
                    "duration_ms": duration_ms
                })

                if not step_success:
                    if feedback:
                        return False, feedback, steps_executed
                    return False, "", steps_executed

        return True, "", steps_executed

    async def _execute_single_step(
        self,
        step: ActionStep,
        task_idx: int,
        step_idx: int,
        action_history: deque,
    ) -> Tuple[bool, str, int]:
        """
        Executes a single ActionStep with retries and vision verification.
        Returns (success: bool, failure_feedback: str, duration_ms: int).
        """
        if self._cancelled:
            return False, "Execution cancelled.", 0

        import time
        for attempt in range(config.max_step_retries + 1):
            if attempt > 0:
                logger.info(
                    "Retrying Worker Step %s.%s (Attempt %s/%s)...",
                    task_idx + 1, step_idx + 1,
                    attempt + 1, config.max_step_retries + 1
                )
            else:
                logger.info(
                    "Worker Step %s.%s: [cyan]%s[/cyan] %s (Method: %s)",
                    task_idx + 1, step_idx + 1,
                    self._enum_val(step.action),
                    step.target,
                    self._enum_val(step.method)
                )

            # Safety gate for dangerous CLI commands
            if self._enum_val(step.method) == "cli" and not self.safety_gate.is_safe(step.target):
                logger.warning("Dangerous CLI command blocked: %s", step.target)
                return False, "Dangerous action blocked by safety gate.", 0

            # General safety check
            if not self.safety_gate.is_safe_action(
                action=self._enum_val(step.action),
                target=step.target,
                method=self._enum_val(step.method)
            ):
                approved = await self.safety_gate.request_approval(step.target)
                if not approved:
                    logger.warning("Action canceled by user. Aborting task.")
                    return False, "", 0

            start_time = time.time()
            # Execute the step
            success, output = await self.executor.execute_step(step.to_dict())

            # Record in sliding-window history
            entry = (
                f"Action: {self._enum_val(step.action)} | Target: {step.target} | "
                f"Method: {self._enum_val(step.method)} | Success: {success} | "
                f"Output: {output[:200]}"
            )
            action_history.append(entry)

            if success:
                logger.info(
                    "[green]Worker Step %s.%s completed:[/green] %s",
                    task_idx + 1, step_idx + 1, output
                )

                # Vision verification if applicable
                _skip = {"", "unknown", "none", "n/a"}
                if step.expected_outcome and step.expected_outcome.strip().lower() not in _skip:
                    v_ok, v_feedback = await self._verify_with_vision(
                        step, task_idx, step_idx, attempt
                    )
                    duration_ms = int((time.time() - start_time) * 1000)
                    if v_ok:
                        if step.undo_action and step.undo_target:
                            self.undo_stack.append(step)
                        if self.event_bus:
                            self.event_bus.publish("step_executed", StepExecutedEvent(
                                step_action=self._enum_val(step.action),
                                step_target=step.target,
                                success=True,
                                message=f"Step succeeded (vision ok): {output}"
                            ))
                        return True, "", duration_ms
                    if v_feedback:
                        if self.event_bus:
                            self.event_bus.publish("step_executed", StepExecutedEvent(
                                step_action=self._enum_val(step.action),
                                step_target=step.target,
                                success=False,
                                message=f"Step failed vision: {v_feedback}"
                            ))
                        return False, v_feedback, duration_ms
                    # v_feedback is empty means retry
                    continue

                # No expected outcome, step succeeds automatically
                if step.undo_action and step.undo_target:
                    self.undo_stack.append(step)
                
                if self.event_bus:
                    self.event_bus.publish("step_executed", StepExecutedEvent(
                        step_action=self._enum_val(step.action),
                        step_target=step.target,
                        success=True,
                        message=f"Step succeeded: {output}"
                    ))
                return True, "", int((time.time() - start_time) * 1000)

            duration_ms = int((time.time() - start_time) * 1000)
            # Execution failed
            logger.error(
                "[red]Worker Step %s.%s failed:[/red] %s",
                task_idx + 1, step_idx + 1, output
            )
            
            if self.event_bus:
                self.event_bus.publish("step_executed", StepExecutedEvent(
                    step_action=self._enum_val(step.action),
                    step_target=step.target,
                    success=False,
                    message=f"Step failed: {output}"
                ))

            active_app = "Unknown"
            import platform
            try:
                system = platform.system()
                if system == "Darwin":
                    proc = await asyncio.create_subprocess_exec(
                        'osascript', '-e',
                        'tell application "System Events" to get name of first application process whose frontmost is true',
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                elif system == "Windows":
                    proc = await asyncio.create_subprocess_exec(
                        'powershell', '-Command',
                        '(Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -First 1).ProcessName',
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                elif system == "Linux":
                    proc = await asyncio.create_subprocess_exec(
                        'xdotool', 'getactivewindow', 'getwindowpid',
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                else:
                    proc = None
                    
                if proc:
                    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
                    if proc.returncode == 0:
                        active_app = stdout.decode().strip()
            except asyncio.TimeoutError:
                logger.debug("Active app check timed out.")
            except Exception as e:
                logger.debug("Failed to get active app: %s", e)

            visible_text = "None"
            if self.verifier.ui_parser:
                visible_text = self.verifier.ui_parser.extract_all_text()
                if len(visible_text) > 1000:
                    visible_text = visible_text[:1000] + "..."

            if attempt < config.max_step_retries:
                logger.info("Step failed, attempting self-correction...")
                prompt = (
                    f"The previous action failed. Here is the error:\n"
                    f"Action: {self._enum_val(step.action)} | Target: {step.target} | Method: {self._enum_val(step.method)}\n"
                    f"Error: {output}\n\n"
                    f"Current Screen State:\n"
                    f"- Active App: {active_app}\n"
                    f"- Visible Text: {visible_text}\n\n"
                    f"Generate a corrected action step to achieve the same goal. Adjust the target or method based on the error."
                )
                try:
                    correction_json = await self.worker.generate_action(prompt, "")
                    corrected_steps = ResponseParser.parse_worker_output(correction_json)
                    if corrected_steps:
                        step = ActionStep.from_dict(corrected_steps[0])
                        logger.info("Correction applied, retrying with new step: %s %s", self._enum_val(step.action), step.target)
                except Exception as e:
                    logger.error("Correction failed, falling back to original step: %s", e)
                    
                await asyncio.sleep(2)
                continue

            feedback = (
                f"\n\n[SYSTEM FEEDBACK]: Worker Step {task_idx + 1}.{step_idx + 1} "
                f"(`{self._enum_val(step.action)}` `{step.target}`) failed with error: {output}.\n"
                f"[CURRENT STATE]:\n"
                f"- Active App: {active_app}\n"
                f"- Visible Text: {visible_text}\n"
                f"CRITICAL INSTRUCTION: DO NOT blindly start from scratch. "
                f"Analyze the failure to understand the current state."
            )
            return False, feedback, duration_ms

        return False, "", 0

    # Dynamic wait times per action type (seconds)
    WAIT_TIMES = {
        "hotkey": 1,
        "type": 2,
        "click": 3,
        "open_app": 4,
        "run_command": 2,
        "goto": 5,
        "sleep": 0,
        "close_browser": 2,
    }

    async def _verify_with_vision(
        self,
        step: ActionStep,
        task_idx: int,
        step_idx: int,
        attempt: int,
    ) -> Tuple[bool, str]:
        """
        Runs vision verification for a completed step.
        Returns (success: bool, failure_feedback: str).
        Empty feedback with success=False means "retry the step".
        """
        # Use dynamic wait time based on the action type
        action_val = self._enum_val(step.action)
        wait = self.WAIT_TIMES.get(action_val, 4)  # type: ignore[attr-defined]
        if wait > 0:
            logger.info("Waiting for UI to render before taking screenshot (%ds)...", wait)
            await asyncio.sleep(wait)

        v_success, v_msg = await self.verifier.verify(
            expected_outcome=step.expected_outcome,
            target_text=step.target,
            action=action_val  # type: ignore[attr-defined]
        )

        if v_success:
            logger.info("[green]Vision Verification passed:[/green] %s", v_msg)
            return True, ""

        logger.warning("[yellow]Vision Verification failed:[/yellow] %s", v_msg)

        if attempt < config.max_step_retries:
            logger.info("Auto-restarting step...")
            await asyncio.sleep(2)
            return False, ""  # empty feedback = retry

        # After all retries exhausted: behavior depends on config
        if config.vision_auto_continue_on_uncertain:
            logger.warning(
                "[yellow]Vision uncertain after %d attempts, but executor reported success. "
                "Auto-continuing (VISION_AUTO_CONTINUE=true)...[/yellow]", attempt + 1
            )
            if step.undo_action and step.undo_target:
                self.undo_stack.append(step)
            return True, ""
        else:
            logger.warning(
                "[yellow]Vision verification failed after %d attempts. "
                "Reporting failure (set VISION_AUTO_CONTINUE=true to override).[/yellow]", attempt + 1
            )
            return False, f"Vision verification failed after {attempt + 1} attempts: {v_msg}"

    async def rollback(self, n: int = -1) -> None:
        """
        Reverses the last `n` steps that have undo actions (or all if `n` = -1).
        """
        if not self.undo_stack:
            return

        limit = len(self.undo_stack) if n == -1 else min(n, len(self.undo_stack))
        logger.info("[yellow]Rolling back %d actions...[/yellow]", limit)

        for _ in range(limit):
            step = self.undo_stack.pop()
            if not step.undo_action or not step.undo_target:
                continue
            
            action_val = self._enum_val(step.action)
            undo_action_val = self._enum_val(step.undo_action)
            logger.info("Reversing action: %s %s -> %s %s", action_val, step.target, undo_action_val, step.undo_target)
            
            # Create a reverse step
            reverse_step = ActionStep(
                action=step.undo_action,
                target=step.undo_target,
                method=step.method, # Assume same method, e.g. cli -> cli
                expected_outcome="none"
            )
            
            try:
                await self.executor.execute_step(reverse_step.to_dict())
            except Exception as e:
                logger.error("Failed to rollback step %s: %s", step.target, e)

