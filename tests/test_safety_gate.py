import pytest
from core.safety_gate import SafetyGate

def test_safety_gate_whitelist():
    gate = SafetyGate()
    # Whitelisted
    assert gate.is_safe("ls -la") is True
    assert gate.is_safe("echo hello") is True
    assert gate.is_safe("pwd") is True
    
    # Not whitelisted -> false
    assert gate.is_safe("rm -rf /") is False
    assert gate.is_safe("sudo rm file") is False
    assert gate.is_safe("format C:") is False
    
    # Metacharacters -> false
    assert gate.is_safe("echo 'hello' > /dev/sda") is False
    assert gate.is_safe("echo test | bash") is False
    assert gate.is_safe("ls & whoami") is False

def test_allowlist():
    gate = SafetyGate()
    gate.allowed_base_commands = {"git"}
    assert gate.is_safe("git status") is True
    assert gate.is_safe("ls -la") is False
    assert gate.is_safe("git log > file") is False
