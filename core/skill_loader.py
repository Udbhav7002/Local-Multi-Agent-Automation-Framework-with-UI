import os
import yaml
from typing import Dict, List, Any
from core.logger import setup_logger

logger = setup_logger("AgentSkillLoader")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENT_SKILLS_DIR = os.path.join(_PROJECT_ROOT, "agent_skills")

class AgentSkillLoader:
    """
    Loads Agent Skills (Claude Skills format) from the agent_skills/ directory.
    Skills are directories containing a SKILL.md file with YAML frontmatter.
    """
    
    def __init__(self) -> None:
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        self.skills.clear()
        if not os.path.exists(_AGENT_SKILLS_DIR):
            os.makedirs(_AGENT_SKILLS_DIR, exist_ok=True)
            return

        for entry in os.listdir(_AGENT_SKILLS_DIR):
            skill_dir = os.path.join(_AGENT_SKILLS_DIR, entry)
            if not os.path.isdir(skill_dir):
                continue

            skill_file = os.path.join(skill_dir, "SKILL.md")
            if not os.path.exists(skill_file):
                continue

            try:
                with open(skill_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # Parse YAML frontmatter
                metadata = {}
                body = content
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        try:
                            metadata = yaml.safe_load(parts[1]) or {}
                        except yaml.YAMLError as ye:
                            logger.warning(f"Failed to parse YAML frontmatter in {skill_file}: {ye}")
                        body = parts[2].strip()

                name = metadata.get("name", entry)
                description = metadata.get("description", "No description provided.")
                
                self.skills[entry] = {
                    "id": entry,
                    "name": name,
                    "description": description,
                    "body": body,
                    "path": skill_file
                }
                logger.debug(f"Loaded Agent Skill: {name} ({entry})")
            except Exception as e:
                logger.error(f"Error loading skill {entry}: {e}")

    def get_all_summaries(self) -> str:
        """Returns a summarized string of all available Agent Skills."""
        if not self.skills:
            return ""
        
        summary = "[AVAILABLE AGENT SKILLS (Claude Skills Hub)]\\n"
        summary += "The user has installed the following domain-expert skills. If the task relates to these domains, YOU MUST STRICTLY follow the instructions in the skill body below.\\n\\n"
        
        for skill_id, data in self.skills.items():
            summary += f"--- SKILL: {data['name']} (ID: {skill_id}) ---\\n"
            summary += f"DESCRIPTION: {data['description']}\\n"
            summary += f"INSTRUCTIONS:\\n{data['body']}\\n\\n"
            
        return summary
