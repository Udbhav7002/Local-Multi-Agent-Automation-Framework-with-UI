from abc import ABC, abstractmethod
from typing import Any

from core.logger import setup_logger
from core.prompt_loader import PromptLoader

logger = setup_logger("BaseAgent")

class BaseAgent(ABC):
    """
    Abstract base class for all core LLM agents (Planner, Worker, Critic, Router).
    Enforces a standard initialization pattern with PromptLoader and LLM client.
    """
    def __init__(self, llm: Any, model_name: str, prompt_loader: PromptLoader) -> None:
        self.llm = llm
        self.model_name = model_name
        self.prompt_loader = prompt_loader

    def _load_prompt(self, agent_name: str, key: str = "system_prompt", **kwargs) -> str:
        """Helper to load a prompt template for this agent."""
        return self.prompt_loader.load(agent_name, key=key, **kwargs)

    @abstractmethod
    async def __call__(self, *args, **kwargs) -> Any:
        """
        Optional: Subclasses can implement a call method for a functional interface,
        or just provide their specific semantic methods (e.g., generate_plan).
        """
        pass
