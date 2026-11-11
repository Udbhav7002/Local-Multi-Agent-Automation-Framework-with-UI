"""
Deterministic benchmark tests for the Local Multi-Agent Automation Framework.

These tests use FakeLLMClient with canned responses to ensure the state machine
executes without flakiness, verifying that the planning/execution pipeline
works correctly for known tasks.
"""
import contextlib

import pytest

from core.events import EventBus
from core.llm_client import FakeLLMClient
from core.plan_execution_engine import PlanExecutionEngine


class MockStepRunner:
    """Mock step runner that simulates successful execution."""
    def __init__(self):
        self.verifier = None

    async def run(self, steps):
        return True, "Success", [{"task": s, "action": "mock", "target": "mock", "success": True} for s in steps]

    async def rollback(self, n=-1):
        pass

    def cancel(self):
        pass


class MockMemoryStore:
    """Mock memory store for testing."""
    def __init__(self):
        self.plans = {}
        self.failures = {}
        self.episodes = []

    async def get_plan(self, task_description):
        return self.plans.get(task_description)

    async def save_plan(self, task_description, plan_json):
        self.plans[task_description] = plan_json

    async def get_failures(self, task_description):
        return self.failures.get(task_description, [])

    async def save_failure(self, task_description, failed_plan, reason):
        self.failures[task_description] = {"plan": failed_plan, "reason": reason}

    async def save_episode(self, episode_data):
        self.episodes.append(episode_data)

    async def get_similar_episodes(self, task_description, limit=3):
        return []

    async def close(self):
        pass

    async def summarize_old_episodes(self, max_episodes=100):
        return 0


@pytest.mark.asyncio
async def test_plan_execution_engine_cached_plan():
    """Test that cached plans are executed correctly."""
    # Create fake LLM that returns a simple plan
    fake_llm = FakeLLMClient(responses=[
        '{"approved": true, "feedback": "Plan looks good"}',  # Critic response
    ])

    # Create mock components
    step_runner = MockStepRunner()
    memory = MockMemoryStore()
    event_bus = EventBus()

    # Create a simple planner that returns a fixed plan
    class MockPlanner:
        def __init__(self, llm):
            self.llm = llm
            self.model_name = "test"

        async def generate_plan(self, prompt):
            return '[{"task": "Open terminal", "action": "open_app", "target": "terminal"}]'

    class MockCritic:
        def __init__(self, llm):
            self.llm = llm
            self.model_name = "test"

        async def verify_plan(self, user_task, plan_json):
            return True, "Plan approved"

    planner = MockPlanner(fake_llm)
    critic = MockCritic(fake_llm)

    engine = PlanExecutionEngine(
        planner=planner,
        critic=critic,
        step_runner=step_runner,
        memory=memory,
        event_bus=event_bus
    )

    # Pre-save a plan
    plan_json = '[{"task": "Open terminal", "action": "open_app", "target": "terminal"}]'
    await memory.save_plan("Open terminal", plan_json)

    # Execute cached plan
    history = []
    result = await engine.execute_cached_plan("Open terminal", plan_json, history, job_id="test-123")

    assert result is True
    assert len(history) == 1
    assert history[0]["outcome"] == "Task completed successfully (cached)."


@pytest.mark.asyncio
async def test_plan_execution_engine_new_plan():
    """Test that new plans are generated and executed."""
    fake_llm = FakeLLMClient(responses=[
        '[{"task": "Open terminal", "action": "open_app", "target": "terminal"}]',  # Planner response
        '{"approved": true, "feedback": "Plan looks good"}',  # Critic response
    ])

    step_runner = MockStepRunner()
    memory = MockMemoryStore()
    event_bus = EventBus()

    class MockPlanner:
        def __init__(self, llm):
            self.llm = llm
            self.model_name = "test"

        async def generate_plan(self, prompt):
            return await self.llm.chat("test", [], format="json")

    class MockCritic:
        def __init__(self, llm):
            self.llm = llm
            self.model_name = "test"

        async def verify_plan(self, user_task, plan_json):
            result = await self.llm.chat("test", [], format="json")
            import json
            data = json.loads(result)
            return data.get("approved", False), data.get("feedback", "")

    planner = MockPlanner(fake_llm)
    critic = MockCritic(fake_llm)

    engine = PlanExecutionEngine(
        planner=planner,
        critic=critic,
        step_runner=step_runner,
        memory=memory,
        event_bus=event_bus
    )

    history = []
    result = await engine.plan_and_execute("Open terminal", history, job_id="test-456")

    assert result is True
    assert len(history) == 1
    assert "completed successfully" in history[0]["outcome"]


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failures():
    """Test that circuit breaker opens after threshold failures."""
    from core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

    breaker = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=60.0)

    async def failing_coro():
        raise ConnectionError("Simulated failure")

    # First 3 failures should be attempted
    for _i in range(3):
        with contextlib.suppress(ConnectionError):
            await breaker.call(failing_coro)

    # Circuit should now be open
    assert breaker.state.name == "OPEN"

    # Next call should fail fast with CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(failing_coro)


@pytest.mark.asyncio
async def test_event_bus_publish_subscribe():
    """Test event bus publish/subscribe mechanism."""
    from core.events import EventBus, SystemEvent

    bus = EventBus()
    received_events = []

    def callback(event):
        received_events.append(event)

    bus.subscribe("test_event", callback)

    event = SystemEvent(source="Test", message="Hello")
    bus.publish("test_event", event)

    assert len(received_events) == 1
    assert received_events[0].message == "Hello"

    # Test unsubscribe
    bus.unsubscribe("test_event", callback)
    bus.publish("test_event", SystemEvent(message="World"))
    assert len(received_events) == 1  # Should not receive second event


@pytest.mark.asyncio
async def test_fake_llm_client():
    """Test FakeLLMClient returns canned responses."""
    fake = FakeLLMClient(responses=['["step 1"]', '{"approved": true}'])

    response1 = await fake.chat("test-model", [{"role": "user", "content": "test"}])
    assert response1 == '["step 1"]'

    response2 = await fake.chat("test-model", [{"role": "user", "content": "test"}])
    assert response2 == '{"approved": true}'

    # Should cycle back
    response3 = await fake.chat("test-model", [{"role": "user", "content": "test"}])
    assert response3 == '["step 1"]'

    assert len(fake.call_log) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
