"""
Protocols (Interfaces) for the Multi-Agent Automation Framework.

This module enforces SOLID principles by ensuring the Orchestrator
and other top-level components depend on abstractions, not concretions.
"""
from typing import Protocol, Optional, Any, Dict, List, Union, AsyncGenerator
from typing import runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Abstract interface for LLM chat completion."""
    
    async def chat(
        self,
        model: str,
        messages: list[dict],
        format: Optional[str] = None,
        images: Optional[list[str]] = None,
        options: Optional[dict] = None,
    ) -> str:
        """Send a chat completion request and return the content string."""
        ...
    
    async def stream_chat(
        self,
        model: str,
        messages: list[dict],
        format: Optional[str] = None,
        images: Optional[list[str]] = None,
        options: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        """Send a chat completion request and stream the response tokens."""
        ...
    
    async def close(self) -> None:
        """Close the underlying client session."""
        ...


@runtime_checkable
class Agent(Protocol):
    """Base interface for any agent in the system."""
    model_name: str
    llm: LLMClient


@runtime_checkable
class TaskPlanner(Agent, Protocol):
    """Interface for agents that generate JSON plans from natural language."""
    llm: LLMClient
    async def generate_plan(self, task_description: str) -> str:
        ...


@runtime_checkable
class TaskWorker(Agent, Protocol):
    """Interface for agents that break down high-level tasks into executable steps."""
    llm: LLMClient
    async def generate_action(self, sub_task: str, current_context: str) -> str:
        ...


@runtime_checkable
class TaskCritic(Agent, Protocol):
    """Interface for agents that evaluate plans for safety and correctness."""
    llm: LLMClient
    async def verify_plan(self, user_task: str, plan_json: str) -> tuple[bool, str]:
        ...


@runtime_checkable
class IntentRouter(Agent, Protocol):
    """Interface for agents that classify the user's intent."""
    llm: LLMClient
    async def classify(self, user_text: str) -> tuple[str, Optional[Any]]:
        ...


@runtime_checkable
class MemoryStore(Protocol):
    """Interface for episodic and semantic memory storage."""
    async def get_plan(self, task_description: str) -> Optional[str]:
        ...

    async def save_plan(self, task_description: str, plan_json: str) -> None:
        ...

    async def get_failures(self, task_description: str) -> list:
        ...

    async def save_failure(self, task_description: str, failed_plan: str, reason: str) -> None:
        ...
        
    async def save_episode(self, episode_data: dict) -> None:
        ...
        
    async def get_similar_episodes(self, task_description: str, limit: int = 3) -> list[dict]:
        ...
        
    async def close(self) -> None:
        """Gracefully release resources (e.g. database locks)."""
        ...


@runtime_checkable
class SkillLibrary(Protocol):
    """Interface for skill library operations."""
    def save_skill(self, task_description: str, plan_json: str) -> None:
        ...
    
    def mark_failure(self, task_description: str) -> None:
        ...
    
    def get_skill_plan(self, task_description: str) -> Optional[str]:
        ...


@runtime_checkable
class AgentLoader(Protocol):
    """Interface for custom agent loader."""
    agents: Dict[str, Any]
    
    def match(self, user_text: str) -> Optional[Any]:
        ...
    
    def get_agent_summary(self) -> str:
        ...


@runtime_checkable
class StepRunnerProtocol(Protocol):
    """Interface for the engine that executes the physical steps."""
    verifier: Any
    async def run(self, steps: List[str]) -> tuple[bool, str, List[Dict[str, Any]]]:
        ...
    async def rollback(self, n: int = -1) -> None:
        ...
