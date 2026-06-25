"""
AgentLoader — loads custom agent definitions from YAML files.
"""
import os
import glob
from dataclasses import dataclass, field
from typing import Optional

from core.logger import setup_logger

logger = setup_logger("AgentLoader")

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    logger.warning("PyYAML not installed. Custom YAML agents will not be available. Install with: pip install pyyaml")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENTS_DIR = os.path.join(_PROJECT_ROOT, "agents")


@dataclass
class CustomAgent:
    """A user-defined agent loaded from a YAML file."""
    name: str
    model: str
    system_prompt: str
    triggers: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    source_file: str = ""

    def matches(self, user_text: str) -> bool:
        """Check if any trigger phrase is a substring of the user's text."""
        text_lower = user_text.lower()
        return any(trigger.lower() in text_lower for trigger in self.triggers)


class AgentLoader:
    """Discovers and loads custom agents from YAML files in the agents/ directory."""

    def __init__(self, agents_dir: str = _AGENTS_DIR) -> None:
        self.agents_dir = agents_dir
        self.agents: dict[str, CustomAgent] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Scan the agents directory and load all YAML files."""
        if not HAS_YAML:
            return

        if not os.path.isdir(self.agents_dir):
            os.makedirs(self.agents_dir, exist_ok=True)
            return

        for filepath in sorted(glob.glob(os.path.join(self.agents_dir, "*.yaml"))):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if not isinstance(data, dict):
                    logger.warning("Skipping %s: not a valid YAML dict", filepath)
                    continue

                name = data.get("name", "")
                if not name:
                    logger.warning("Skipping %s: missing 'name' field", filepath)
                    continue

                agent = CustomAgent(
                    name=name,
                    model=data.get("model", ""),
                    system_prompt=data.get("system_prompt", ""),
                    triggers=data.get("triggers", []),
                    tools=data.get("tools", []),
                    source_file=filepath,
                )
                self.agents[name] = agent
                logger.info("Loaded custom agent: '%s' (triggers: %s)", name, agent.triggers)

            except Exception as e:
                logger.warning("Failed to load agent from %s: %s", filepath, e)

    def match(self, user_text: str) -> Optional[CustomAgent]:
        """Find the first custom agent whose triggers match the user's text."""
        for agent in self.agents.values():
            if agent.matches(user_text):
                return agent
        return None

    def get_agent_names(self) -> list[str]:
        """Return the names of all loaded custom agents."""
        return list(self.agents.keys())

    def get_agent_summary(self) -> str:
        """Return a summary of available custom agents for prompt injection."""
        if not self.agents:
            return ""
        lines = []
        for agent in self.agents.values():
            tools_str = ", ".join(agent.tools) if agent.tools else "default"
            lines.append(f"- {agent.name} (triggers: {', '.join(agent.triggers)}, tools: {tools_str})")
        return "Available custom agents:\n" + "\n".join(lines)
