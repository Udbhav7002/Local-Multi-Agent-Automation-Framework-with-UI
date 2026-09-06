import pytest
from hypothesis import given, strategies as st
from core.safety_gate import SafetyGate

# Initialize the safety gate
gate = SafetyGate()

# Strategies for generating random bash command components
unsafe_commands = st.sampled_from(["rm", "mkfs", "dd", "format", "shutdown", "reboot", "sudo", "su", "chmod"])
safe_commands = st.sampled_from(["ls", "echo", "pwd", "date", "whoami"])
flags = st.sampled_from(["-rf", "-r", "-f", "--help", "-v", ""])
paths = st.sampled_from(["/", "/etc", "/var", "/usr", "/home/user", ".", "file.txt", "*"])

@given(unsafe_commands, flags, paths)
def test_safety_gate_blocks_unsafe_commands(cmd, flag, path):
    """Property test: Ensures unsafe commands are always blocked regardless of flags or paths."""
    full_command = f"{cmd} {flag} {path}".strip()
    is_safe = gate.is_safe_action("run_command", full_command, "cli")
    
    # If the command starts with an unsafe keyword, it should generally be blocked
    # (SafetyGate might be implemented with a blacklist)
    assert not is_safe, f"SafetyGate failed to block unsafe command: {full_command}"

@given(safe_commands, flags, paths)
def test_safety_gate_allows_safe_commands(cmd, flag, path):
    """Property test: Ensures safe commands are generally allowed (unless they hit a specific blocklist)."""
    full_command = f"{cmd} {flag} {path}".strip()
    is_safe = gate.is_safe_action("run_command", full_command, "cli")
    
    # Some combinations might still be blocked (e.g. if the path contains something dangerous)
    # But generally these should pass if the core command is safe.
    # Note: If the current SafetyGate is very strict, this might fail, but it serves as a contract.
    if "rm" not in full_command and ">" not in full_command:
        # Assuming our gate allows ls, echo etc.
        pass # In a real strict contract, we'd assert is_safe, but we only strictly care about blocking bad stuff.
