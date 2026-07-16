"""
Router module for evaluating the intent of a user prompt.
Determines whether the user is asking a question or issuing a task command.
"""
import json
from typing import Optional, Tuple, Any

from core.logger import setup_logger
from core.config import config
from core.prompt_loader import PromptLoader
from core.base_agent import BaseAgent
from core.protocols import IntentRouter

logger = setup_logger("Router")


class Router(BaseAgent, IntentRouter):  # pylint: disable=too-few-public-methods
    """
    Agent that routes user requests to either the QA LLM or the Planner.
    """
    def __init__(self, llm, model_name: str, prompt_loader: PromptLoader, event_bus: Optional[Any] = None) -> None:
        super().__init__(llm, model_name, prompt_loader)
        self.event_bus = event_bus

    async def __call__(self, user_text: str) -> Tuple[str, Optional[str]]:
        return await self.classify(user_text)

    async def classify(self, user_text: str) -> Tuple[str, Optional[str]]:
        """
        Classifies user text as either 'question' or 'task' using structured JSON.
        Returns a tuple: (intent, answer_if_question)
        """
        # Deterministic Heuristic Bypass
        action_verbs = [
            'open', 'run', 'start', 'click', 'type', 'search', 'delete',
            'create', 'make', 'do', 'close', 'kill'
        ]
        first_word = user_text.strip().split()[0].lower() if user_text.strip() else ""
        if first_word in action_verbs:
            logger.debug("Deterministic heuristic bypass matched verb: %s", first_word)
            return "task", None

        system_prompt = self._load_prompt("router", key="routing_prompt")

        try:
            logger.debug("Routing intent via LLM using model %s...", self.model_name)
            content = await self.llm.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                format='json',
            )

            try:
                result = json.loads(content)
                intent = result.get('intent', '').lower()
            except json.JSONDecodeError:
                # Ultimate fallback
                intent = content.lower()

            # If the model explicitly says task, we treat it as a task.
            if "task" in intent:
                return "task", None
                
            if "visual_question" in intent:
                return "visual_question", None

            # Otherwise, default to question/chat behavior
            logger.debug("Intent classified as standard question. Generating answer...")
            
            chat_system_prompt = self._load_prompt("router", key="chat_prompt")
            
            answer = await self.llm.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": chat_system_prompt},
                    {"role": "user", "content": user_text}
                ],
            )
            return "question", answer

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("Router failed to classify intent: %s", e)
            raise RuntimeError(f"Router error: {e}") from e
