import pytest
from core.planning_context import PlanningContext


class TestPlanningContextTruncation:
    @pytest.mark.asyncio
    async def test_within_budget_no_truncation(self):
        """Verify prompt is unchanged when within max_prompt_chars budget."""
        ctx = PlanningContext(
            original_task="Build landing page",
            user_preferences="Use dark theme",
            conversation_history=[{"prompt": "Hi", "outcome": "Hello"}],
            system_feedback=["Feedback 1"],
            max_prompt_chars=1000,
        )
        prompt = await ctx.build_prompt()
        assert "Build landing page" in prompt
        assert "Use dark theme" in prompt
        assert 'User said: "Hi"' in prompt
        assert "Feedback 1" in prompt

    @pytest.mark.asyncio
    async def test_fifo_truncation_drops_oldest_conversation_history_first(self):
        """Verify oldest conversation history entry is dropped before newer ones."""
        ctx = PlanningContext(
            original_task="Task Keep Intact",
            conversation_history=[
                {"prompt": "OldestPrompt", "outcome": "OldestOutcome"},
                {"prompt": "NewerPrompt", "outcome": "NewerOutcome"},
            ],
            system_feedback=["Feedback Latest"],
            max_prompt_chars=160,
        )
        prompt = await ctx.build_prompt()
        assert "Task Keep Intact" in prompt
        assert "Feedback Latest" in prompt
        assert "NewerPrompt" in prompt
        assert "OldestPrompt" not in prompt

    @pytest.mark.asyncio
    async def test_fifo_truncation_drops_oldest_feedback_preserves_newest(self):
        """Verify oldest feedback entries are dropped FIFO while newest feedback is preserved."""
        ctx = PlanningContext(
            original_task="Important Task Description",
            system_feedback=[
                "SYSTEM_ERR_OLD_1: Initial failure reason that is long",
                "SYSTEM_ERR_OLD_2: Second failure reason that is long",
                "SYSTEM_ERR_NEWEST: Latest error feedback that must be preserved",
            ],
            max_prompt_chars=140,
        )
        prompt = await ctx.build_prompt()
        assert "Important Task Description" in prompt
        assert "SYSTEM_ERR_NEWEST: Latest error feedback that must be preserved" in prompt
        assert "SYSTEM_ERR_OLD_1" not in prompt

    @pytest.mark.asyncio
    async def test_preserves_original_task_and_newest_feedback_under_tight_budget(self):
        """Verify original_task and system_feedback[-1] are strictly preserved under tight budget."""
        ctx = PlanningContext(
            original_task="CoreTaskIntact",
            conversation_history=[{"prompt": "OldHistory", "outcome": "Failed"}],
            system_feedback=["OldFB", "NewestFB"],
            max_prompt_chars=20,
        )
        prompt = await ctx.build_prompt()
        assert "CoreTaskIntact" in prompt
        assert "NewestFB" in prompt
        assert "OldHistory" not in prompt
        assert "OldFB" not in prompt

    def test_fit_to_budget_sync_fallback_sections(self):
        """Verify _fit_to_budget_sync direct list fallback preserves index 0 and index -1."""
        ctx = PlanningContext(original_task="TaskBase", max_prompt_chars=30)
        sections = ["TaskBase", "MiddleOldSection", "NewestFeedbackEnd"]
        result = ctx._fit_to_budget_sync(sections)
        assert "TaskBase" in result
        assert "NewestFeedbackEnd" in result
        assert "MiddleOldSection" not in result
