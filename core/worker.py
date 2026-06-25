"""
Worker module for handling specialized sub-tasks assigned by the Manager (Planner).
"""
from core.config import config
from core.logger import setup_logger
from core.config import config
from core.logger import setup_logger
from core.response_parser import ResponseParser
from core.protocols import TaskWorker
from core.events import SystemEvent, EventBus
from core.prompt_loader import PromptLoader
from core.base_agent import BaseAgent

logger = setup_logger("Worker")


class Worker(BaseAgent):
    """
    Executes a specific sub-task given by the Manager.
    Outputs low-level CLI, GUI, or Browser commands in JSON.
    """
    def __init__(self, llm, model_name: str, prompt_loader: PromptLoader, event_bus: EventBus = None) -> None:
        super().__init__(llm, model_name, prompt_loader)
        self.event_bus = event_bus

    async def __call__(self, sub_task: str, current_context: str) -> str:
        return await self.generate_action(sub_task, current_context)

    async def generate_action(self, sub_task: str, current_context: str) -> str:
        """
        Takes a specific sub-task and context, and generates the exact JSON step.
        """
        system_prompt = self._load_prompt("worker", os_context=config.os_context)

        prompt = f"Context:\n{current_context}\n\nYour Sub-Task:\n{sub_task}"

        logger.debug("Worker (%s) generating action for sub-task: %s", self.model_name, sub_task)
        if self.event_bus:
            self.event_bus.publish("agent_action", SystemEvent(
                source="Worker", level="DEBUG", message=f"Worker parsing sub-task: {sub_task}"
            ))

        try:
            content = await self.llm.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
            )

            # Use centralized response parser
            return ResponseParser.clean_and_extract_json(content, shape="array")

        except Exception as e:
            logger.error("Worker failed: %s", e)
            raise e
