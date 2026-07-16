import pytest
import json
from core.step_runner import StepRunner
from core.safety_gate import SafetyGate

class FakeWorker:
    def __init__(self, mock_response: str):
        self.mock_response = mock_response

    async def generate_action(self, sub_task: str, current_context: str) -> str:
        return self.mock_response

@pytest.mark.asyncio
async def test_step_runner_success(fake_executor, fake_verifier):
    mock_json = json.dumps([
        {
            "action": "run_command",
            "target": "echo hello",
            "method": "cli",
            "expected_outcome": "none"
        }
    ])
    worker = FakeWorker(mock_json)
    runner = StepRunner(worker, fake_executor, fake_verifier, SafetyGate())

    success, feedback, steps_exec = await runner.run(["do something"])
    
    assert success is True
    assert feedback == ""
    assert len(steps_exec) == 1
    assert len(fake_executor.executed_steps) == 1
    assert fake_executor.executed_steps[0]["action"] == "run_command"

@pytest.mark.asyncio
async def test_step_runner_executor_failure(fake_executor, fake_verifier):
    mock_json = json.dumps([
        {
            "action": "run_command",
            "target": "fail_command",
            "method": "cli",
            "expected_outcome": "none"
        }
    ])
    worker = FakeWorker(mock_json)
    gate = SafetyGate()
    gate.allowed_base_commands.add("fail_command")  # bypass safety gate
    runner = StepRunner(worker, fake_executor, fake_verifier, gate)

    fake_executor.mock_success = False
    fake_executor.mock_output = "Command not found"

    success, feedback, steps_exec = await runner.run(["do something"])
    
    assert success is False
    assert "Command not found" in feedback
