"""
Orchestrator module for the Local Multi-Agent Automation Framework.
Handles routing and delegates execution to the PlanExecutionEngine.
"""
from collections import deque
from typing import Optional

from rich.panel import Panel
from rich.live import Live
from rich.markdown import Markdown

from core.logger import setup_logger, console
from core.protocols import TaskPlanner, TaskCritic, TaskWorker, IntentRouter, MemoryStore, StepRunnerProtocol
from core.agent_loader import AgentLoader
from memory.preferences import UserPreferences
from memory.skill_library import SkillLibrary
from core.plan_execution_engine import PlanExecutionEngine
from core.custom_agent_runner import CustomAgentRunner
from core.sanitizer import InputSanitizer, PromptInjectionError
from core.policies import ExecutionPolicy, PolicyResolution

logger = setup_logger("Orchestrator")


class Orchestrator:
    """
    The central coordinator. Thin wrapper that delegates routing to the IntentRouter
    and planning/execution to the PlanExecutionEngine.
    """
    def __init__(
            self,
            router: IntentRouter,
            planner: TaskPlanner,
            critic: TaskCritic,
            worker: TaskWorker,
            step_runner: StepRunnerProtocol,
            memory: MemoryStore,
            preferences: Optional[UserPreferences] = None,
            skill_library: Optional[SkillLibrary] = None,
            agent_loader: Optional[AgentLoader] = None,
            event_bus=None
            ) -> None:
        self.router = router
        self.planner = planner
        self.critic = critic
        self.worker = worker
        self.step_runner = step_runner
        self.memory = memory
        self.preferences = preferences or UserPreferences()
        self.skill_library = skill_library or SkillLibrary()
        self.agent_loader = agent_loader
        self.event_bus = event_bus

        self._conversation_history: deque = deque(maxlen=5)
        self.sanitizer = InputSanitizer()

        self.custom_agent_runner = CustomAgentRunner(
            planner_llm=self.planner.llm,
            step_runner=self.step_runner,
            default_model_name=self.planner.model_name
        )

        self.engine = PlanExecutionEngine(
            planner=self.planner,
            critic=self.critic,
            step_runner=self.step_runner,
            memory=self.memory,
            preferences=self.preferences,
            skill_library=self.skill_library,
            agent_loader=self.agent_loader,
            custom_agent_runner=self.custom_agent_runner,
            event_bus=self.event_bus
        )

        self.policy = ExecutionPolicy(
            memory=self.memory,
            skill_library=self.skill_library,
            router=self.router,
            agent_loader=self.agent_loader
        )

    async def shutdown(self) -> None:
        """Gracefully shut down all resources."""
        # Cancel in-flight steps
        if hasattr(self.step_runner, 'cancel'):
            self.step_runner.cancel()

        # Close LLM client (if it has a close method) - only close once since all agents share the same MultiLLMClient
        seen_llms = set()
        for agent in (self.router, self.planner, self.critic, self.worker):
            if hasattr(agent, 'llm') and hasattr(agent.llm, 'close'):
                llm_id = id(agent.llm)
                if llm_id not in seen_llms:
                    seen_llms.add(llm_id)
                    try:
                        await agent.llm.close()
                    except Exception as e:
                        logger.warning("Failed to close LLM client: %s", e)
        
        # Close step runner executor
        if hasattr(self.step_runner, 'executor') and hasattr(self.step_runner.executor, 'shutdown'):
            try:
                await self.step_runner.executor.shutdown()
            except Exception as e:
                logger.warning("Failed to close executor: %s", e)
        
        # Close memory store
        if hasattr(self.memory, 'close'):
            try:
                await self.memory.close()
            except Exception as e:
                logger.warning("Failed to close memory: %s", e)
        
        logger.info("Orchestrator shutdown complete")

    async def process_prompt(self, user_text: str, job_id: str = "") -> bool:
        """Main entry point for processing user input. Returns True on success, False on failure."""
        if not getattr(self, "_prefs_loaded", False):
            await self.preferences.load()
            self._prefs_loaded = True
            
        try:
            user_text = self.sanitizer.sanitize(user_text)
        except PromptInjectionError as e:
            logger.error("Prompt injection rejected: %s", e)
            return False
            
        logger.info("[bold cyan]Orchestrator received prompt:[/bold cyan] %s", user_text)
             
        import uuid
        from core.logger import set_task_id
        
        task_id = str(uuid.uuid4())[:8]
        set_task_id(task_id)
        logger.info("[task:%s] Processing user input: '%s'", task_id, user_text)

        # Delegate to Policy Engine
        logger.info("Resolving execution policy...")
        try:
            resolution, payload = await self.policy.resolve(user_text)
        except Exception as e:
            logger.error("Policy resolution failed: %s", e)
            return False

        if resolution == PolicyResolution.CACHED_PLAN:
            logger.info("[bold green]Found successful plan in memory! Bypassing planner...[/bold green]")
            return await self.engine.execute_cached_plan(user_text, payload, list(self._conversation_history), job_id=job_id)
            
        elif resolution == PolicyResolution.SKILL_PLAN:
            logger.info("[bold green]Found matching skill in library! Bypassing planner...[/bold green]")
            return await self.engine.execute_cached_plan(user_text, payload, list(self._conversation_history), job_id=job_id)
            
        elif resolution == PolicyResolution.QUESTION:
            answer = ""
            with Live(Panel("...", title="Agent Answer", border_style="blue"), refresh_per_second=10) as live:
                async for chunk in payload:
                    answer += chunk
                    live.update(Panel(Markdown(answer), title="Agent Answer", border_style="blue"))
            self._conversation_history.append({"prompt": user_text, "outcome": "Answered as a standard question."})
            return True
            
        elif resolution == PolicyResolution.VISUAL_QUESTION:
            logger.info("Delegating visual question to Vision Verifier...")
            answer = await self.step_runner.verifier.ask(user_text)
            console.print(Panel(answer, title="Vision Agent Answer", border_style="green"))
            self._conversation_history.append({"prompt": user_text, "outcome": "Answered as a visual question."})
            return True
            
        elif resolution == PolicyResolution.CUSTOM_AGENT:
            matched_agent = payload
            logger.info("[bold magenta]Delegating to custom agent: '%s'[/bold magenta]", matched_agent.name)
            success = await self.custom_agent_runner.run_custom_agent(user_text, matched_agent)
            if success:
                self._conversation_history.append({"prompt": user_text, "outcome": f"Completed by {matched_agent.name}."})
                return True
            else:
                self._conversation_history.append({"prompt": user_text, "outcome": f"Failed (agent: {matched_agent.name})."})
                logger.info("Falling back to default planning pipeline...")
                return await self.engine.plan_and_execute(user_text, list(self._conversation_history), job_id=job_id)
                
        elif resolution == PolicyResolution.FULL_PLAN:
            logger.info("[bold cyan]Identified as a TASK. Planning execution...[/bold cyan]")
            return await self.engine.plan_and_execute(user_text, list(self._conversation_history), job_id=job_id)
        
        return False
