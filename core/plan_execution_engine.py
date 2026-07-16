import json
import time
import asyncio
from datetime import datetime
from typing import Tuple, Optional

from rich.panel import Panel

from core.config import config
from core.logger import setup_logger, console
from core.protocols import TaskPlanner, TaskCritic, StepRunnerProtocol, MemoryStore
from core.events import TaskStartedEvent, TaskCompletedEvent
from core.agent_loader import AgentLoader
from memory.preferences import UserPreferences
from memory.skill_library import SkillLibrary
from core.planning_context import PlanningContext
from core.custom_agent_runner import CustomAgentRunner

logger = setup_logger("PlanExecutionEngine")

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

class PlanExecutionEngine:
    """Handles the core loop of planning, executing, and evaluating tasks."""
    def __init__(
        self,
        planner: TaskPlanner,
        critic: TaskCritic,
        step_runner: StepRunnerProtocol,
        memory: MemoryStore,
        preferences: Optional[UserPreferences] = None,
        skill_library: Optional[SkillLibrary] = None,
        agent_loader: Optional[AgentLoader] = None,
        custom_agent_runner: Optional[CustomAgentRunner] = None,
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

    async def execute_cached_plan(self, user_text: str, plan_json: str, history: list) -> bool:
        """Fast-path execution for pre-verified plans."""
        self.event_bus.publish("task_started", TaskStartedEvent(
            task_description=user_text,
            message=f"Starting cached task: {user_text}"
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
                self.memory.save_episode(episode)
                history.append({"prompt": user_text, "outcome": "Task completed successfully (cached)."})
                self.event_bus.publish("task_completed", TaskCompletedEvent(
                    task_description=user_text,
                    success=True,
                    total_duration_s=round(time.time() - task_start_time, 2),
                    message="Cached task completed successfully."
                ))
            else:
                self.event_bus.publish("task_completed", TaskCompletedEvent(
                    task_description=user_text,
                    success=False,
                    total_duration_s=round(time.time() - task_start_time, 2),
                    message="Cached task failed."
                ))
            return plan_success
        except Exception as e:
            logger.error("Error executing cached plan: %s", e)
            return False

    async def execute_step_groups(self, groups: list[list[dict]]) -> Tuple[bool, str, list]:
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
                
                async def _delegate(step):
                    agent_name = step["delegate_to"]
                    agent = agent_loader.agents.get(agent_name)
                    if agent:
                        await custom_agent_runner.run_custom_agent(step["task"], agent)
                    else:
                        logger.warning("Delegated agent '%s' not found.", agent_name)
                        await step_runner.run([step["task"]])

                await asyncio.gather(*(_delegate(s) for s in delegated_steps))

            if normal_tasks:
                if len(normal_tasks) == 1:
                    plan_success, failure_feedback, steps_exec = await self.step_runner.run(normal_tasks)
                    all_steps_executed.extend(steps_exec)
                    if not plan_success:
                        break
                else:
                    logger.info("[bold cyan]Executing %d tasks in parallel...[/bold cyan]", len(normal_tasks))
                    results = await asyncio.gather(*(self.step_runner.run([task]) for task in normal_tasks))
                    for success, feedback, steps_exec in results:
                        all_steps_executed.extend(steps_exec)
                        if not success:
                            plan_success = False
                            failure_feedback = feedback
                            break
                    if not plan_success:
                        break

        return plan_success, failure_feedback, all_steps_executed

    async def plan_and_execute(self, user_text: str, history: list) -> bool:
        """The main loop: generate plan, evaluate with critic, and execute."""
        self.event_bus.publish("task_started", TaskStartedEvent(
            task_description=user_text,
            message=f"Starting task: {user_text}"
        ))
        
        task_start_time = time.time()
        
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
            
        ctx.conversation_history = list(history)
        ctx.past_failures = self.memory.get_failures(user_text)
        
        if ctx.past_failures:
            logger.warning("[yellow]Loaded %s past failure(s) into Planner context.[/yellow]", len(ctx.past_failures))

        for plan_attempt in range(config.max_plan_regenerations):
            if plan_attempt > 0:
                logger.info("[magenta]Requesting new plan (Attempt %s/%s)...[/magenta]", plan_attempt + 1, config.max_plan_regenerations)
            else:
                logger.info("Generating step-by-step plan...")

            try:
                plan_json = await self.planner.generate_plan(await ctx.build_prompt())
                steps = json.loads(plan_json)
                if not isinstance(steps, list) or not all(isinstance(s, dict) and "task" in s for s in steps):
                    raise ValueError("Generated plan is not a JSON array of objects with 'task' keys.")

                plan_text = ""
                for idx, step in enumerate(steps):
                    para = " (Parallel)" if step.get("parallel") else ""
                    plan_text += f"[bold]{idx + 1}.[/bold] [cyan]Goal[/cyan] -> {step['task']}{para}\n"
                console.print(Panel(plan_text.strip(), title=f"Execution Plan ({len(steps)} steps)", border_style="magenta"))

            except (json.JSONDecodeError, ValueError) as e:
                logger.error("Error parsing plan: %s", e)
                ctx.add_feedback(f"\n\n[SYSTEM FEEDBACK]: Previous response was not valid JSON. Error: {e}.\nCRITICAL INSTRUCTION: You MUST output ONLY a valid JSON array.")
                continue
            except Exception as e:
                logger.error("Planner exception: %s", e)
                ctx.add_feedback(f"\n\n[SYSTEM FEEDBACK]: Generation failed: {e}.\nCRITICAL INSTRUCTION: Fix the error and generate a valid plan.")
                continue

            logger.info("Passing plan to Critic for evaluation...")
            is_approved, critic_feedback = await self.critic.verify_plan(user_text, plan_json)

            if not is_approved:
                logger.warning("[red]Critic rejected the plan:[/red] %s. Regenerating...", critic_feedback)
                ctx.add_feedback(f"\n\n[SYSTEM FEEDBACK]: Critic rejected plan. Reason: {critic_feedback}\nCRITICAL INSTRUCTION: You MUST fix these issues and generate a new plan.")
                continue

            logger.info("[green]Critic approved the plan.[/green]")

            groups = _group_steps_for_parallel(steps)
            plan_success, failure_feedback, all_steps_executed = await self.execute_step_groups(groups)

            if plan_success:
                logger.info("[bold green]Task Complete.[/bold green]")
                self.memory.save_plan(user_text, plan_json)
                
                episode = {
                    "task": user_text,
                    "plan": steps,
                    "steps_executed": all_steps_executed,
                    "outcome": "success",
                    "total_duration_s": round(time.time() - task_start_time, 2),
                    "timestamp": datetime.now().isoformat()
                }
                self.memory.save_episode(episode)
                
                if self.preferences:
                    for s in all_steps_executed:
                        if s.get("action") == "open_app":
                            await self.preferences.log_app_usage(s.get("target"))

                if self.skill_library:
                    self.skill_library.save_skill(user_text, plan_json)

                history.append({"prompt": user_text, "outcome": "Task completed successfully."})
                self.event_bus.publish("task_completed", TaskCompletedEvent(
                    task_description=user_text,
                    success=True,
                    total_duration_s=round(time.time() - task_start_time, 2),
                    message="Task completed successfully."
                ))
                return True

            if failure_feedback:
                logger.warning("Plan failed. Passing feedback to planner for a new strategy...")
                self.memory.save_failure(user_text, plan_json, failure_feedback.strip())
                if self.skill_library:
                    self.skill_library.mark_failure(user_text)
                ctx.add_feedback(failure_feedback)
                continue

            self.memory.save_failure(user_text, plan_json, "User aborted or catastrophic error")
            self.event_bus.publish("task_completed", TaskCompletedEvent(
                task_description=user_text,
                success=False,
                total_duration_s=round(time.time() - task_start_time, 2),
                message="Task aborted or catastrophic error."
            ))
            return False

        logger.error("[bold red]Task failed completely after maximum plan regenerations. Rolling back...[/bold red]")
        await self.step_runner.rollback()
        history.append({"prompt": user_text, "outcome": "Task failed after max retries."})
        self.event_bus.publish("task_completed", TaskCompletedEvent(
            task_description=user_text,
            success=False,
            total_duration_s=round(time.time() - task_start_time, 2),
            message="Task failed after maximum retries."
        ))
        return False
