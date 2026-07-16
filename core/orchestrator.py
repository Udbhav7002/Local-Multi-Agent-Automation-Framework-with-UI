"""
Orchestrator module for the Local Multi-Agent Automation Framework.
Handles routing and delegates execution to the PlanExecutionEngine.
"""
from collections import deque
from typing import Optional

from rich.panel import Panel

from core.logger import setup_logger, console
from core.protocols import TaskPlanner, TaskCritic, TaskWorker, IntentRouter, MemoryStore, StepRunnerProtocol
from core.agent_loader import AgentLoader
from memory.preferences import UserPreferences
from memory.skill_library import SkillLibrary
from core.plan_execution_engine import PlanExecutionEngine
from core.custom_agent_runner import CustomAgentRunner

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

    async def shutdown(self) -> None:
        """Gracefully shut down all resources."""
        # Close LLM client (if it has a close method)
        for agent in (self.router, self.planner, self.critic, self.worker):
            if hasattr(agent, 'llm') and hasattr(agent.llm, 'close'):
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
                self.memory.close()
            except Exception as e:
                logger.warning("Failed to close memory: %s", e)
        
        logger.info("Orchestrator shutdown complete")

    async def process_prompt(self, user_text: str) -> None:
        """Main entry point for processing user input."""
        if not getattr(self, "_prefs_loaded", False):
            await self.preferences.load()
            self._prefs_loaded = True
             
        logger.info("Processing user input: '%s'", user_text)

        # 1. Fast paths: Memory Cache
        cached_plan = self.memory.get_plan(user_text)
        if cached_plan:
            logger.info("[bold green]Found successful plan in memory! Bypassing planner...[/bold green]")
            await self.engine.execute_cached_plan(user_text, cached_plan, list(self._conversation_history))
            return

        # 1.5. Fast paths: Skill Library
        if self.skill_library:
            skill_plan = self.skill_library.get_skill_plan(user_text)
            if skill_plan:
                logger.info("[bold green]Found matching skill in library! Bypassing planner...[/bold green]")
                await self.engine.execute_cached_plan(user_text, skill_plan, list(self._conversation_history))
                return

        # 2. Routing
        logger.info("Routing intent...")
        try:
            intent, response = await self.router.classify(user_text)
        except Exception as e:
            logger.error("Routing failed: %s", e)
            return

        if intent == "question":
            console.print(Panel(response, title="Agent Answer", border_style="blue"))
            self._conversation_history.append({"prompt": user_text, "outcome": "Answered as a standard question."})
            return

        if intent == "visual_question":
            logger.info("Delegating visual question to Vision Verifier...")
            answer = await self.step_runner.verifier.ask(user_text)
            console.print(Panel(answer, title="Vision Agent Answer", border_style="green"))
            self._conversation_history.append({"prompt": user_text, "outcome": "Answered as a visual question."})
            return

        logger.info("[bold cyan]Identified as a TASK. Planning execution...[/bold cyan]")

        # 2.5 Custom Agent early exit
        if self.agent_loader:
            matched_agent = self.agent_loader.match(user_text)
            if matched_agent:
                logger.info("[bold magenta]Delegating to custom agent: '%s'[/bold magenta]", matched_agent.name)
                success = await self.custom_agent_runner.run_custom_agent(user_text, matched_agent)
                if success:
                    self._conversation_history.append({"prompt": user_text, "outcome": f"Completed by {matched_agent.name}."})
                else:
                    self._conversation_history.append({"prompt": user_text, "outcome": f"Failed (agent: {matched_agent.name})."})
                    logger.info("Falling back to default planning pipeline...")
                    await self.engine.plan_and_execute(user_text, list(self._conversation_history))
                return

        # 3. Execution
        await self.engine.plan_and_execute(user_text, list(self._conversation_history))
