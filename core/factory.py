"""
FrameworkBuilder (Factory/Container) module.
Handles dependency injection and instantiating the entire framework
from configuration. This keeps main.py perfectly clean.
"""

from core.config import config
from core.llm_client import OllamaClient
from core.prompt_loader import PromptLoader
from core.router import Router
from core.planner import Planner
from core.critic import Critic
from core.worker import Worker
from core.step_runner import StepRunner
from core.executor import ExecutorDispatcher
from core.safety_gate import SafetyGate
from core.orchestrator import Orchestrator
from core.agent_loader import AgentLoader
from vision.verifier import VisionVerifier
from vision.ui_parser import UIParser
from memory.chroma_store import ChromaStore
from memory.preferences import UserPreferences
from memory.skill_library import SkillLibrary


class FrameworkBuilder:
    """IoC Container that builds the application graph."""

    @staticmethod
    def build_orchestrator() -> Orchestrator:
        from core.events import EventBus
        event_bus = EventBus()

        # 1. LLM Client — single async instance shared by all agents
        llm = OllamaClient(num_ctx=config.num_ctx, keep_alive=0)

        # 2. Common Utilities
        ui_parser = UIParser()
        prompt_loader = PromptLoader()

        # 3. Agents — all receive LLMClient, PromptLoader, and event_bus
        router = Router(llm=llm, model_name=config.manager_model, prompt_loader=prompt_loader, event_bus=event_bus)
        planner = Planner(llm=llm, model_name=config.manager_model, prompt_loader=prompt_loader, event_bus=event_bus)
        critic = Critic(llm=llm, model_name=config.manager_model, prompt_loader=prompt_loader, event_bus=event_bus)
        worker = Worker(llm=llm, model_name=config.worker_model, prompt_loader=prompt_loader, event_bus=event_bus)
        verifier = VisionVerifier(llm=llm, model_name=config.vision_model, ui_parser=ui_parser)

        # 4. Executor — Strategy pattern with dispatcher
        executor = ExecutorDispatcher(ui_parser)

        # 5. Safety + Step execution
        safety_gate = SafetyGate(llm=llm, model_name=config.manager_model, prompt_loader=prompt_loader)
        step_runner = StepRunner(
            worker=worker,
            executor=executor,
            verifier=verifier,
            safety_gate=safety_gate,
            event_bus=event_bus
        )

        # 6. Memory & Sub-systems
        memory = ChromaStore()
        preferences = UserPreferences()
        skill_library = SkillLibrary()
        agent_loader = AgentLoader()

        # 7. Orchestrator — central hub
        return Orchestrator(
            router=router,
            planner=planner,
            critic=critic,
            worker=worker,
            step_runner=step_runner,
            memory=memory,
            preferences=preferences,
            skill_library=skill_library,
            agent_loader=agent_loader,
            event_bus=event_bus
        )
