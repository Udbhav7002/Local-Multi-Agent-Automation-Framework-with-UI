"""
Execution policies for determining how to handle a user request.
"""
from enum import Enum, auto
from typing import Any

from core.protocols import AgentLoader, IntentRouter, MemoryStore, SkillLibrary


class PolicyResolution(Enum):
    CACHED_PLAN = auto()
    SKILL_PLAN = auto()
    QUESTION = auto()
    VISUAL_QUESTION = auto()
    CUSTOM_AGENT = auto()
    FULL_PLAN = auto()


class ExecutionPolicy:
    """
    Decouples the decision-making logic from the Orchestrator.
    Determines the correct path for a given user request based on memory,
    skills, and router classification.
    """
    def __init__(
        self,
        memory: MemoryStore,
        skill_library: SkillLibrary,
        router: IntentRouter,
        agent_loader: AgentLoader | None
    ):
        self.memory = memory
        self.skill_library = skill_library
        self.router = router
        self.agent_loader = agent_loader

    async def resolve(self, user_text: str) -> tuple[PolicyResolution, Any]:
        """
        Resolves the policy for the user_text.
        Returns a tuple of (PolicyResolution, Payload).
        Payload varies by resolution type:
        - CACHED_PLAN / SKILL_PLAN -> plan string
        - QUESTION / VISUAL_QUESTION -> response/answer string (or None)
        - CUSTOM_AGENT -> Agent matching object
        - FULL_PLAN -> None
        """
        # 1. Fast paths: Memory Cache
        if self.memory:
            cached_plan = await self.memory.get_plan(user_text)
            if cached_plan:
                return PolicyResolution.CACHED_PLAN, cached_plan

        # 2. Fast paths: Skill Library
        if self.skill_library:
            skill_plan = self.skill_library.get_skill_plan(user_text)
            if skill_plan:
                return PolicyResolution.SKILL_PLAN, skill_plan

        # 3. Routing
        if self.router:
            intent, response = await self.router.classify(user_text)
            if intent == "question":
                return PolicyResolution.QUESTION, response
            if intent == "visual_question":
                return PolicyResolution.VISUAL_QUESTION, None

        # 4. Custom Agent matching
        if self.agent_loader:
            matched_agent = self.agent_loader.match(user_text)
            if matched_agent:
                return PolicyResolution.CUSTOM_AGENT, matched_agent

        # 5. Fallback to full planning and execution
        return PolicyResolution.FULL_PLAN, None
