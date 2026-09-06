"""
PlanningContext — structured prompt builder for the planning loop.

Replaces the brittle `current_prompt_context += ...` pattern in the
Orchestrator with a type-safe dataclass that:
  - Keeps all context components separate and inspectable.
  - Enforces a token budget so the prompt never silently overflows
    the LLM's context window.
  - Summarizes oldest feedback when reaching 80% capacity.
  - Truncates oldest feedback first (FIFO) to stay within budget as a fallback.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanningContext:
    """Accumulates context for the Planner across retry iterations."""

    original_task: str
    user_preferences: str = ""
    os_context: str = ""
    conversation_history: list[dict] = field(default_factory=list)
    available_agents: str = ""
    agent_skills: str = ""
    past_failures: list[dict] = field(default_factory=list)
    system_feedback: list[str] = field(default_factory=list)

    # Approximate character budget (not tokens — we use ~4 chars/token heuristic).
    # Default 24 000 chars ≈ 6 000 tokens, leaving headroom in an 8 192-token window.
    max_prompt_chars: int = 24_000

    llm: Any = None
    model_name: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_feedback(self, feedback: str) -> None:
        """Append system feedback from a failed plan attempt."""
        self.system_feedback.append(feedback)

    def _render_sections(self) -> list[str]:
        """Render prompt sections from dataclass attributes."""
        sections: list[str] = [self.original_task]

        if self.user_preferences:
            sections.append(
                f"\n\n[USER PREFERENCES]: {self.user_preferences}"
            )

        if self.available_agents:
            sections.append(
                f"\n\n[AVAILABLE AGENTS]: {self.available_agents}"
            )

        if self.agent_skills:
            sections.append(
                f"\n\n{self.agent_skills}"
            )

        if self.conversation_history:
            history_block = "\n\n[CONVERSATION HISTORY] (most recent last):\n"
            for entry in self.conversation_history:
                history_block += (
                    f"- User said: \"{entry['prompt']}\" → "
                    f"Outcome: {entry['outcome']}\n"
                )
            sections.append(history_block)

        if self.past_failures:
            failure_block = (
                "\n\n[REFLECTION MEMORY] Warning: The following strategies "
                "failed previously for this or a similar task. "
                "DO NOT REPEAT THEM.\n"
            )
            for failure in self.past_failures:
                failure_block += (
                    f"- Failed Plan: {failure['plan']}\n"
                    f"  Reason: {failure['reason']}\n"
                )
            sections.append(failure_block)

        # Feedback is appended last so it's trimmed in FIFO order.
        for fb in self.system_feedback:
            sections.append(fb)

        return sections

    async def build_prompt(self) -> str:
        """Render all context into a single prompt string for the Planner.
        """
        # Trigger summarization if we are nearing the budget
        current_est = len(self.original_task) + len(str(self.past_failures)) + len(str(self.conversation_history))
        for fb in self.system_feedback:
            current_est += len(fb)
            
        if current_est > (self.max_prompt_chars * 0.8) and self.llm and self.model_name:
            await self._summarize()

        sections = self._render_sections()
        return self._fit_to_budget_sync(sections)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _summarize(self):
        """Summarizes history and failures into a dense block."""
        from core.logger import setup_logger
        logger = setup_logger("PlanningContext")
        
        prompt = "Summarize the following past failures and conversation history into dense, concise bullet points highlighting key lessons learned to avoid repeating mistakes. Be extremely brief.\n\n"
        if self.past_failures:
            prompt += "PAST FAILURES:\n" + str(self.past_failures) + "\n\n"
        if self.conversation_history:
            prompt += "CONVERSATION HISTORY:\n" + str(self.conversation_history) + "\n\n"
        
        try:
            logger.info("Context window nearing 80%. Summarizing history...")
            summary = await self.llm.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            self.past_failures = [{"plan": "Summarized Context", "reason": summary}]
            self.conversation_history = []
            logger.info("[cyan]Context summarized successfully to save tokens.[/cyan]")
        except Exception as e:
            logger.error(f"Context summarization failed: {e}")

    def _fit_to_budget_sync(self, sections: list[str] = None) -> str:
        """Truncate prompt sections in FIFO order to stay within max_prompt_chars.

        Guarantees:
        - original_task is ALWAYS preserved intact.
        - Most recent error feedback (system_feedback[-1]) is ALWAYS preserved.
        - Oldest conversation history and oldest system feedback entries are dropped first (FIFO).
        """
        is_direct_sections = sections is not None
        if sections is None:
            sections = self._render_sections()

        if len("".join(sections)) <= self.max_prompt_chars:
            return "".join(sections)

        # 1. Drop oldest entries from conversation_history (FIFO order)
        while self.conversation_history and len("".join(self._render_sections())) > self.max_prompt_chars:
            self.conversation_history.pop(0)

        # 2. Drop oldest entries from system_feedback (FIFO order), preserving system_feedback[-1]
        while len(self.system_feedback) > 1 and len("".join(self._render_sections())) > self.max_prompt_chars:
            self.system_feedback.pop(0)

        # 3. Drop oldest entries from past_failures (FIFO order)
        while self.past_failures and len("".join(self._render_sections())) > self.max_prompt_chars:
            self.past_failures.pop(0)

        # If context state was modified, re-render sections from state
        if not is_direct_sections or (self.conversation_history or len(self.system_feedback) > 0 or self.past_failures):
            rendered = self._render_sections()
            if len("".join(rendered)) <= self.max_prompt_chars:
                return "".join(rendered)
            sections = rendered

        # Fallback for direct sections list or if state truncation wasn't enough
        # Drop from index 1 (oldest section after original_task), preserving sections[0] and sections[-1]
        sections = list(sections)
        while len(sections) > 2 and len("".join(sections)) > self.max_prompt_chars:
            sections.pop(1)

        return "".join(sections)

