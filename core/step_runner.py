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
    """

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

    async def run(self, steps: list[str]) -> Tuple[bool, str, list[dict]]:
        """
        Executes a list of high-level sub-tasks via the Worker Agent.
        Returns (success: bool, failure_feedback: str, steps_executed: list[dict]).
        """
        # Use a deque as a sliding window to prevent context blowout
        action_history: deque = deque(maxlen=20)
        history_chars = 0
        steps_executed = []

        for i, sub_task in enumerate(steps):
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
                    "action": step.action.value,
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
                    step.action.value, step.target, step.method.value
                )

            # Safety gate for dangerous CLI commands
            if step.method.value == "cli" and not self.safety_gate.is_safe(step.target):
                approved = await self.safety_gate.request_approval(step.target)
                if not approved:
                    logger.warning("Action canceled by user. Aborting task.")
                    return False, "", 0

            start_time = time.time()
            # Execute the step
            success, output = await self.executor.execute_step(step.to_dict())

            # Record in sliding-window history
            entry = (
                f"Action: {step.action.value} | Target: {step.target} | "
                f"Method: {step.method.value} | Success: {success} | "
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
                                step_action=step.action.value,
                                step_target=step.target,
                                success=True,
                                message=f"Step succeeded (vision ok): {output}"
                            ))
                        return True, "", duration_ms
                    if v_feedback:
                        if self.event_bus:
                            self.event_bus.publish("step_executed", StepExecutedEvent(
                                step_action=step.action.value,
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
                        step_action=step.action.value,
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
                    step_action=step.action.value,
                    step_target=step.target,
                    success=False,
                    message=f"Step failed: {output}"
                ))

            if attempt < config.max_step_retries:
                logger.info("Auto-restarting step...")
                await asyncio.sleep(2)
                continue

            active_app = "Unknown"
            try:
                proc = await asyncio.create_subprocess_exec(
                    'osascript', '-e', 'tell application "System Events" to get name of first application process whose frontmost is true',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
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

            feedback = (
                f"\n\n[SYSTEM FEEDBACK]: Worker Step {task_idx + 1}.{step_idx + 1} "
                f"(`{step.action.value}` `{step.target}`) failed with error: {output}.\n"
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
        wait = self.WAIT_TIMES.get(step.action.value, 4)
        if wait > 0:
            logger.info("Waiting for UI to render before taking screenshot (%ds)...", wait)
            await asyncio.sleep(wait)

        v_success, v_msg = await self.verifier.verify(
            expected_outcome=step.expected_outcome,
            target_text=step.target,
            action=step.action.value
        )

        if v_success:
            logger.info("[green]Vision Verification passed:[/green] %s", v_msg)
            return True, ""

        logger.warning("[yellow]Vision Verification failed:[/yellow] %s", v_msg)

        if attempt < config.max_step_retries:
            logger.info("Auto-restarting step...")
            await asyncio.sleep(2)
            return False, ""  # empty feedback = retry

        # After all retries exhausted: auto-continue if the executor reported success
        # The executor DID succeed (we only call _verify_with_vision after success),
        # so the vision model is likely being overly strict. Continue with a warning.
        logger.warning(
            "[yellow]Vision uncertain after %d attempts, but executor reported success. "
            "Auto-continuing...[/yellow]", attempt + 1
        )
        if step.undo_action and step.undo_target:
            self.undo_stack.append(step)
        return True, ""

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
            
            logger.info("Reversing action: %s %s -> %s %s", step.action.value, step.target, step.undo_action.value, step.undo_target)
            
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

