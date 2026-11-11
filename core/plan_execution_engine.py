import asyncio
import json
import time
from datetime import datetime
from enum import Enum, auto

from rich.panel import Panel

from core.agent_loader import AgentLoader
from core.config import config
from core.custom_agent_runner import CustomAgentRunner
from core.events import TaskCompletedEvent, TaskStartedEvent, TaskStateChangedEvent
from core.logger import console, setup_logger
from core.planning_context import PlanningContext
from core.protocols import MemoryStore, StepRunnerProtocol, TaskCritic, TaskPlanner
from core.skill_loader import AgentSkillLoader
from memory.preferences import UserPreferences
from memory.skill_library import SkillLibrary

logger = setup_logger("PlanExecutionEngine")


class TaskState(Enum):
    PLANNING = auto()
    CRITIQUING = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    FAILED = auto()


def _group_steps_for_parallel(steps: list[dict]) -> list[list[dict]]:
    """Groups steps into sub-lists that can be run concurrently."""
    groups = []
    current_group = []
    for s in steps:
        if s.get("parallel"):
            current_group.append(s)
        else:
            if current_group:
                groups.append(current_group)
                current_group = []
            groups.append([s])
    if current_group:
        groups.append(current_group)
    return groups


def _flatten_htn(steps: list[dict]) -> list[dict]:
    """Flattens a Hierarchical Task Network into a linear list of leaf steps."""
    flat = []
    for step in steps:
        if step.get("subtasks"):
            flat.extend(_flatten_htn(step["subtasks"]))
        else:
            flat.append(step)
    return flat


def _format_htn(node_list: list[dict], indent: int = 0) -> str:
    """Format HTN plan for display."""
    text = ""
    for idx, step in enumerate(node_list):
        para = " (Parallel)" if step.get("parallel") else ""
        prefix = "  " * indent + f"[bold]{idx + 1}.[/bold]"
        text += f"{prefix} [cyan]Goal[/cyan] -> {step['task']}{para}\n"
        if step.get("subtasks"):
            text += _format_htn(step["subtasks"], indent + 1)
    return text

class PlanExecutionEngine:
    """Handles the core loop of planning, executing, and evaluating tasks."""
    def __init__(
        self,
        planner: TaskPlanner,
        critic: TaskCritic,
        step_runner: StepRunnerProtocol,
        memory: MemoryStore,
        preferences: UserPreferences | None = None,
        skill_library: SkillLibrary | None = None,
        agent_loader: AgentLoader | None = None,
        custom_agent_runner: CustomAgentRunner | None = None,
        event_bus=None
    ) -> None:
        self.planner = planner
        self.critic = critic
        self.step_runner = step_runner
        self.memory = memory
        self.preferences = preferences
        self.skill_library = skill_library
        self.agent_loader = agent_loader
        self.custom_agent_runner = custom_agent_runner
        self.event_bus = event_bus

    async def execute_cached_plan(self, user_text: str, plan_json: str, history: list, job_id: str = "") -> bool:
        """Fast-path execution for pre-verified plans."""
        if self.event_bus:
            self.event_bus.publish("task_started", TaskStartedEvent(
                task_description=user_text,
                message=f"Starting cached task: {user_text}",
                job_id=job_id
            ))

        task_start_time = time.time()
        try:
            steps = json.loads(plan_json)
            if not isinstance(steps, list):
                logger.error("Invalid plan format.")
                return False

            groups = _group_steps_for_parallel(steps)
            plan_success, _, all_steps_executed = await self.execute_step_groups(groups)

            if plan_success:
                episode = {
                    "task": user_text,
                    "plan": steps,
                    "steps_executed": all_steps_executed,
                    "outcome": "success",
                    "total_duration_s": round(time.time() - task_start_time, 2),
                    "timestamp": datetime.now().isoformat()
                }
                await self.memory.save_episode(episode)
                history.append({"prompt": user_text, "outcome": "Task completed successfully (cached)."})
                if self.event_bus:
                    self.event_bus.publish("task_completed", TaskCompletedEvent(
                        task_description=user_text,
                        success=True,
                        total_duration_s=round(time.time() - task_start_time, 2),
                        message="Cached task completed successfully.",
                        job_id=job_id
                    ))
            else:
                if self.event_bus:
                    self.event_bus.publish("task_completed", TaskCompletedEvent(
                        task_description=user_text,
                        success=False,
                        total_duration_s=round(time.time() - task_start_time, 2),
                        message="Cached task failed.",
                        job_id=job_id
                    ))
            return plan_success
        except Exception as e:
            logger.error("Error executing cached plan: %s", e)
            return False

    async def execute_step_groups(self, groups: list[list[dict]]) -> tuple[bool, str, list]:
        """Executes groups of steps, supporting delegation and concurrency."""
        plan_success = True
        failure_feedback = ""
        all_steps_executed = []

        for group in groups:
            delegated_steps = [s for s in group if s.get("delegate_to")]
            normal_tasks = [s["task"] for s in group if not s.get("delegate_to")]

            if delegated_steps and self.custom_agent_runner and self.agent_loader:
                logger.info("[bold magenta]Delegating %d tasks to custom agents...[/bold magenta]", len(delegated_steps))

                agent_loader = self.agent_loader
                custom_agent_runner = self.custom_agent_runner
                step_runner = self.step_runner

                async def _delegate(
                    step,
                    agent_loader=agent_loader,
                    custom_agent_runner=custom_agent_runner,
                    step_runner=step_runner,
                ):
                    agent_name = step["delegate_to"]
                    agent = agent_loader.agents.get(agent_name)
                    if agent:
                        await custom_agent_runner.run_custom_agent(step["task"], agent)
                    else:
                        logger.warning("Delegated agent '%s' not found.", agent_name)
                        await step_runner.run([step["task"]])

                await asyncio.gather(*(_delegate(s) for s in delegated_steps), return_exceptions=True)

            if normal_tasks:
                if len(normal_tasks) == 1:
                    plan_success, failure_feedback, steps_exec = await self.step_runner.run(normal_tasks)
                    all_steps_executed.extend(steps_exec)
                    if not plan_success:
                        break
                else:
                    logger.info("[bold cyan]Executing %d tasks in parallel...[/bold cyan]", len(normal_tasks))
                    results = await asyncio.gather(*(self.step_runner.run([task]) for task in normal_tasks), return_exceptions=True)
                    for result in results:
                        if isinstance(result, BaseException):
                            logger.error("Parallel task failed with exception: %s", result)
                            plan_success = False
                            failure_feedback = str(result)
                            break
                        success, feedback, steps_exec = result
                        all_steps_executed.extend(steps_exec)
                        if not success:
                            plan_success = False
                            failure_feedback = feedback
                            break
                    if not plan_success:
                        break

        return plan_success, failure_feedback, all_steps_executed

    async def plan_and_execute(self, user_text: str, history: list, job_id: str = "") -> bool:
        """The main loop: generate plan, evaluate with critic, and execute using a State Machine."""
        current_state = TaskState.PLANNING

        await self._publish_task_started(user_text, job_id)

        task_start_time = time.time()

        ctx = await self._build_planning_context(user_text, history)

        plan_attempt = 0
        plan_json = ""
        steps: list = []
        all_steps_executed: list = []

        while current_state not in (TaskState.COMPLETED, TaskState.FAILED):
            if current_state == TaskState.PLANNING:
                plan_json, steps = await self._generate_and_validate_plan(ctx, plan_attempt)
                if plan_json:
                    await self._publish_state_change(user_text, job_id, TaskState.CRITIQUING)
                    current_state = TaskState.CRITIQUING
                else:
                    plan_attempt += 1
                    if plan_attempt >= config.max_plan_regenerations:
                        logger.error("[bold red]Task failed completely after maximum plan regenerations. Rolling back...[/bold red]")
                        await self.step_runner.rollback()
                        current_state = TaskState.FAILED
                        await self._publish_state_change(user_text, job_id, TaskState.FAILED)
                    continue

            elif current_state == TaskState.CRITIQUING:
                approved = await self._critique_plan(user_text, plan_json)
                if approved:
                    logger.info("[green]Critic approved the plan.[/green]")
                    current_state = TaskState.EXECUTING
                    await self._publish_state_change(user_text, job_id, TaskState.EXECUTING)
                else:
                    plan_attempt += 1
                    current_state = TaskState.PLANNING
                    await self._publish_state_change(user_text, job_id, TaskState.PLANNING)

            elif current_state == TaskState.EXECUTING:
                plan_success, failure_feedback, all_steps_executed = await self._execute_plan(steps)

                if plan_success:
                    current_state = TaskState.COMPLETED
                    await self._publish_state_change(user_text, job_id, TaskState.COMPLETED)
                else:
                    current_state = await self._handle_execution_failure(
                        user_text, plan_json, failure_feedback, ctx, plan_attempt, job_id
                    )
                    plan_attempt += 1

        # Final outcomes
        if current_state == TaskState.COMPLETED:
            return await self._finalize_success(user_text, plan_json, steps, all_steps_executed, task_start_time, history, job_id)
        else:
            return await self._finalize_failure(user_text, plan_json, task_start_time, history, job_id)

    async def _publish_task_started(self, user_text: str, job_id: str) -> None:
        if self.event_bus:
            self.event_bus.publish("task_started", TaskStartedEvent(
                task_description=user_text,
                message=f"Starting task: {user_text}",
                job_id=job_id
            ))

    async def _publish_state_change(self, user_text: str, job_id: str, new_state: TaskState) -> None:
        if self.event_bus:
            self.event_bus.publish("task_state_changed", TaskStateChangedEvent(
                task_description=user_text,
                job_id=job_id,
                new_state=new_state.name
            ))

    async def _build_planning_context(self, user_text: str, history: list) -> PlanningContext:
        ctx = PlanningContext(
            original_task=user_text,
            max_prompt_chars=config.max_prompt_chars,
            llm=self.planner.llm,
            model_name=self.planner.model_name
        )

        if self.preferences:
            ctx.user_preferences = self.preferences.get_context_string()

        if self.agent_loader:
            ctx.available_agents = self.agent_loader.get_agent_summary()

        skill_loader = AgentSkillLoader()
        ctx.agent_skills = skill_loader.get_all_summaries()

        ctx.conversation_history = list(history)
        ctx.past_failures = await self.memory.get_failures(user_text)

        if ctx.past_failures:
            logger.warning("[yellow]Loaded %s past failure(s) into Planner context.[/yellow]", len(ctx.past_failures))

        return ctx

    async def _generate_and_validate_plan(self, ctx: PlanningContext, plan_attempt: int) -> tuple[str, list]:
        if plan_attempt > 0:
            logger.info("[magenta]Requesting new plan (Attempt %s/%s)...[/magenta]", plan_attempt + 1, config.max_plan_regenerations)
        else:
            logger.info("Generating step-by-step plan...")

        try:
            plan_json = await self.planner.generate_plan(await ctx.build_prompt())
            steps = json.loads(plan_json)
            if not isinstance(steps, list) or not all(isinstance(s, dict) and "task" in s for s in steps):
                raise ValueError("Generated plan is not a JSON array of objects with 'task' keys.")

            plan_text = _format_htn(steps)
            console.print(Panel(plan_text.strip(), title="Hierarchical Execution Plan", border_style="magenta"))

            return plan_json, steps

        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Error parsing plan: %s", e)
            ctx.add_feedback(f"\n\n[SYSTEM FEEDBACK]: Previous response was not valid JSON. Error: {e}.\nCRITICAL INSTRUCTION: You MUST output ONLY a valid JSON array.")
        except Exception as e:
            logger.error("Planner exception: %s", e)
            ctx.add_feedback(f"\n\n[SYSTEM FEEDBACK]: Generation failed: {e}.\nCRITICAL INSTRUCTION: Fix the error and generate a valid plan.")

        return "", []

    async def _critique_plan(self, user_text: str, plan_json: str) -> bool:
        logger.info("Passing plan to Critic for evaluation...")
        is_approved, critic_feedback = await self.critic.verify_plan(user_text, plan_json)

        if not is_approved:
            logger.warning("[red]Critic rejected the plan:[/red] %s. Regenerating...", critic_feedback)
            return False
        return True

    async def _execute_plan(self, steps: list) -> tuple[bool, str, list]:
        flat_steps = _flatten_htn(steps)
        groups = _group_steps_for_parallel(flat_steps)
        return await self.execute_step_groups(groups)

    async def _handle_execution_failure(
        self,
        user_text: str,
        plan_json: str,
        failure_feedback: str,
        ctx: PlanningContext,
        plan_attempt: int,
        job_id: str,
    ) -> TaskState:
        if failure_feedback:
            logger.warning("Plan failed. Passing feedback to planner for a new strategy...")
            await self.memory.save_failure(user_text, plan_json, failure_feedback.strip())
            if self.skill_library:
                self.skill_library.mark_failure(user_text)
            ctx.add_feedback(failure_feedback)
            return TaskState.PLANNING
        else:
            await self.memory.save_failure(user_text, plan_json, "User aborted or catastrophic error")
            return TaskState.FAILED

    async def _finalize_success(
        self,
        user_text: str,
        plan_json: str,
        steps: list,
        all_steps_executed: list,
        task_start_time: float,
        history: list,
        job_id: str,
    ) -> bool:
        logger.info("[bold green]Task Complete.[/bold green]")
        await self.memory.save_plan(user_text, plan_json)

        episode = {
            "task": user_text,
            "plan": steps,
            "steps_executed": all_steps_executed,
            "outcome": "success",
            "total_duration_s": round(time.time() - task_start_time, 2),
            "timestamp": datetime.now().isoformat()
        }
        await self.memory.save_episode(episode)

        if self.preferences:
            for s in all_steps_executed:
                if s.get("action") == "open_app":
                    await self.preferences.log_app_usage(s.get("target"))

        if self.skill_library:
            self.skill_library.save_skill(user_text, plan_json)

        history.append({"prompt": user_text, "outcome": "Task completed successfully."})
        if self.event_bus:
            self.event_bus.publish("task_completed", TaskCompletedEvent(
                task_description=user_text,
                success=True,
                total_duration_s=round(time.time() - task_start_time, 2),
                message="Task completed successfully.",
                job_id=job_id
            ))
        return True

    async def _finalize_failure(
        self,
        user_text: str,
        plan_json: str,
        task_start_time: float,
        history: list,
        job_id: str,
    ) -> bool:
        history.append({"prompt": user_text, "outcome": "Task failed."})
        if self.event_bus:
            self.event_bus.publish("task_completed", TaskCompletedEvent(
                task_description=user_text,
                success=False,
                total_duration_s=round(time.time() - task_start_time, 2),
                message="Task failed or aborted.",
                job_id=job_id
            ))
        return False
