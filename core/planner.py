"""
Planner module for breaking down user tasks into actionable JSON steps.
"""
from core.config import config
from core.logger import setup_logger
from core.response_parser import ResponseParser
from core.protocols import TaskPlanner
from core.events import SystemEvent, EventBus
from core.prompt_loader import PromptLoader
from core.base_agent import BaseAgent
import json
from typing import Optional

logger = setup_logger("Planner")


class Planner(BaseAgent, TaskPlanner):
    """
    Agent that generates a sequential plan of actions for the framework to execute.
    """
    def __init__(self, llm, model_name: str, prompt_loader: PromptLoader, event_bus: Optional[EventBus] = None) -> None:
        super().__init__(llm, model_name, prompt_loader)
        self.event_bus = event_bus

    async def __call__(self, task_description: str) -> str:
        return await self.generate_plan(task_description)

    async def generate_plan(self, task_description: str) -> str:
        """
        Takes a task and outputs a strict JSON array of high-level sub-tasks.
        """
        system_prompt = self._load_prompt("planner", os_context=config.os_context)

        logger.debug("Generating plan using model %s...", self.model_name)
        if self.event_bus:
            self.event_bus.publish("agent_action", SystemEvent(
                source="Planner", level="INFO", message="Generating step-by-step plan..."
            ))
        try:
            content = await self.llm.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": task_description}
                ],
            )

            # Use centralized response parser
            return ResponseParser.clean_and_extract_json(content, shape="array")

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("Planner failed to generate plan due to parsing/validation error: %s", e)
            raise e
