"""
Critic module for evaluating proposed execution plans.
Ensures safety, logic, and adherence to rules before execution.
"""
import json
from typing import Tuple
from core.protocols import TaskCritic
from core.events import SystemEvent, EventBus
from core.logger import setup_logger
from core.prompt_loader import PromptLoader
from core.base_agent import BaseAgent

logger = setup_logger("Critic")

class Critic(BaseAgent, TaskCritic):  # pylint: disable=too-few-public-methods
    """
    Agent that verifies plans before execution for safety, efficiency, and correctness.
    """
    def __init__(self, llm, model_name: str, prompt_loader: PromptLoader, event_bus: EventBus = None) -> None:
        super().__init__(llm, model_name, prompt_loader)
        self.event_bus = event_bus

    async def __call__(self, user_task: str, plan_json: str) -> Tuple[bool, str]:
        return await self.verify_plan(user_task, plan_json)

    async def verify_plan(self, user_task: str, plan_json: str) -> Tuple[bool, str]:
        """
        Evaluates a proposed JSON plan against the user's task.
        Ensures the plan makes logical sense and contains no inherently dangerous steps.
        Returns (approved: bool, feedback: str)
        """
        system_prompt = self._load_prompt("critic")

        user_prompt = f"USER TASK: {user_task}\n\nPROPOSED PLAN:\n{plan_json}"

        try:
            if self.event_bus:
                self.event_bus.publish("agent_action", SystemEvent(
                    source="Critic", level="INFO", message="Passing plan to Critic for evaluation..."
                ))

            content = await self.llm.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                format='json',
            )

            try:
                result = json.loads(content)
                is_approved = result.get('approved', False)
                feedback = result.get('feedback', 'No feedback provided.')

                if is_approved:
                    if self.event_bus:
                        self.event_bus.publish("agent_action", SystemEvent(
                            source="Critic", level="SUCCESS", message="Critic approved the plan!"
                        ))
                else:
                    if self.event_bus:
                        self.event_bus.publish("agent_action", SystemEvent(
                            source="Critic", level="WARNING", message=f"Critic rejected plan: {feedback}"
                        ))

                return is_approved, feedback
            except json.JSONDecodeError:
                logger.error("Critic output invalid JSON: %s", content)
                return False, f"Critic failed to output valid JSON: {content}"

        except Exception as e:
            logger.error("Critic evaluation failed: %s", e)
            return False, f"Critic encountered an error: {e}"
