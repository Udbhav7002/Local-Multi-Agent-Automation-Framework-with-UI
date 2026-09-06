"""
Custom exceptions for the Local Multi-Agent Automation Framework.
"""

class AgentFrameworkError(Exception):
    """Base exception for all framework-related errors."""
    pass

class LLMTimeoutError(AgentFrameworkError):
    """Raised when an LLM inference call times out or fails completely."""
    pass

class SafetyBlockedError(AgentFrameworkError):
    """Raised when a command is blocked by the SafetyGate."""
    pass



class PlanParsingError(AgentFrameworkError):
    """Raised when the LLM outputs invalid JSON that cannot be parsed into an execution plan."""
    pass
