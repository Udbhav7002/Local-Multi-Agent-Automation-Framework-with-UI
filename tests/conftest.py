import pytest
from core.models import ActionStep, MethodType

class FakeLLMClient:
    """A fake LLM client for testing without network calls."""
    def __init__(self, responses: list[str] = None):
        self.responses = responses or []
        self.call_count = 0
        self.last_prompt = ""

    async def chat(self, model: str, messages: list[dict], format: str = None) -> str:
        self.call_count += 1
        self.last_prompt = str(messages)
        if self.responses:
            return self.responses.pop(0)
        return '{"result": "mocked"}'

class FakeExecutor:
    """A fake Executor for testing StepRunner."""
    def __init__(self):
        self.executed_steps = []
        self.mock_success = True
        self.mock_output = "Mocked output"

    async def execute_step(self, step_dict: dict) -> tuple[bool, str]:
        self.executed_steps.append(step_dict)
        return self.mock_success, self.mock_output

class FakeVerifier:
    """A fake Vision Verifier."""
    def __init__(self):
        self.ui_parser = None
        self.mock_success = True
        self.mock_feedback = "Looks good"

    async def verify(self, expected_outcome: str, target_text: str, action: str) -> tuple[bool, str]:
        return self.mock_success, self.mock_feedback

@pytest.fixture
def fake_llm():
    return FakeLLMClient()

@pytest.fixture
def fake_executor():
    return FakeExecutor()

@pytest.fixture
def fake_verifier():
    return FakeVerifier()
