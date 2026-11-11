"""
Router module for evaluating the intent of a user prompt.
Determines whether the user is asking a question or issuing a task command.
"""
import json
from typing import Any

from core.base_agent import BaseAgent
from core.logger import setup_logger
from core.prompt_loader import PromptLoader
from core.protocols import IntentRouter

logger = setup_logger("Router")


class Router(BaseAgent, IntentRouter):  # pylint: disable=too-few-public-methods
    """
    Agent that routes user requests to either the QA LLM or the Planner.
    """
    def __init__(self, llm, model_name: str, prompt_loader: PromptLoader, event_bus: Any | None = None) -> None:
        super().__init__(llm, model_name, prompt_loader)
        self.event_bus = event_bus

    async def __call__(self, user_text: str) -> tuple[str, str | None]:
        return await self.classify(user_text)

    async def classify(self, user_text: str) -> tuple[str, Any | None]:
        """
        Classifies user text as either 'question' or 'task' using structured JSON.
        Returns a tuple: (intent, answer_if_question)
        """
        # Deterministic Heuristic Bypass — check if any early word is an action verb
        action_verbs = {
            'open', 'run', 'start', 'click', 'type', 'search', 'delete',
            'create', 'make', 'do', 'close', 'kill', 'launch', 'execute',
            'install', 'download', 'navigate', 'go', 'find', 'take',
        }
        words = user_text.strip().lower().split()
        # Check first 3 words (covers "please open", "can you run", etc.)
        leading_words = words[:3] if len(words) >= 3 else words
        if any(word in action_verbs for word in leading_words):
            matched = [w for w in leading_words if w in action_verbs][0]
            logger.debug("Deterministic heuristic bypass matched verb: %s", matched)
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

            answer_stream = self.llm.stream_chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": chat_system_prompt},
                    {"role": "user", "content": user_text}
                ],
            )
            return "question", answer_stream

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("Router failed to classify intent: %s", e)
            raise RuntimeError(f"Router error: {e}") from e
