import os
import string
from typing import Optional, Any, Dict

import yaml

from core.logger import setup_logger

logger = setup_logger("PromptLoader")

_PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts"
)


class PromptLoader:
    """Loads and caches prompt templates from YAML files in the prompts/ directory."""

    def __init__(self, prompts_dir: str = _PROMPTS_DIR) -> None:
        self._dir = prompts_dir
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _load_file(self, agent_name: str) -> Dict[str, Any]:
        if agent_name in self._cache:
            return self._cache[agent_name]
        path = os.path.join(self._dir, f"{agent_name}.yaml")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Prompt file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict):
                data = {}
        self._cache[agent_name] = data
        return data

    def load(self, agent_name: str, key: str = "system_prompt", **kwargs) -> str:
        """Load a prompt template and render it with the given variables.
        
        Args:
            agent_name: The name of the agent (e.g., 'planner', 'worker').
            key: The YAML key to load (default: 'system_prompt').
            **kwargs: Template variables to substitute (e.g., os_context='...').
        
        Returns:
            The rendered prompt string.
        """
        data = self._load_file(agent_name)
        template = data.get(key, "")
        if not template:
            raise ValueError(f"Key '{key}' not found in {agent_name}.yaml")
        # Use jinja2.Template for advanced rendering
        import jinja2
        try:
            return jinja2.Template(template).render(**kwargs)  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning("Failed to render Jinja2 template for %s/%s: %s", agent_name, key, e)
            return template  # type: ignore[no-any-return]

    def reload(self) -> None:
        """Clear the cache to force reloading from disk."""
        self._cache.clear()
