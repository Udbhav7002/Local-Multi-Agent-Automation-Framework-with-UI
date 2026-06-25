"""
Skill library for caching and reusing successful action sequences.
"""
import os
import json
import re
from datetime import datetime
from typing import Optional

from core.logger import setup_logger

logger = setup_logger("SkillLibrary")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKILLS_DIR = os.path.join(_PROJECT_ROOT, "skills")

class SkillLibrary:
    """Manages reusable skills generated from past successful plans."""
    
    def __init__(self) -> None:
        if not os.path.exists(_SKILLS_DIR):
            os.makedirs(_SKILLS_DIR, exist_ok=True)

    def _get_safe_name(self, text: str) -> str:
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', text.lower())[:50].strip('_')
        return safe_name

    def save_skill(self, task_description: str, plan_json: str) -> None:
        """Saves a successful plan as a reusable skill."""
        safe_name = self._get_safe_name(task_description)
        if not safe_name:
            return
            
        file_path = os.path.join(_SKILLS_DIR, f"{safe_name}.json")
        
        # Base skill structure
        skill = {
            "skill_id": safe_name,
            "trigger_phrases": [task_description.lower()],
            "plan_json": plan_json,
            "success_count": 0,
            "fail_count": 0,
            "last_used": ""
        }
        
        # Load existing if it exists to merge data
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    skill.update(existing)
                    
                # Update plan in case the new one is better/different
                skill["plan_json"] = plan_json
                    
                # Add trigger phrase if new
                task_lower = task_description.lower()
                if task_lower not in skill["trigger_phrases"]:
                    skill["trigger_phrases"].append(task_lower)
            except Exception as e:
                logger.error("Failed to read existing skill %s: %s", file_path, e)
                
        skill["success_count"] += 1
        skill["last_used"] = datetime.now().isoformat()
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(skill, f, indent=4)
            logger.debug("Saved skill '%s' to library.", safe_name)
        except Exception as e:
            logger.error("Failed to save skill: %s", e)

    def mark_failure(self, task_description: str) -> None:
        """Mark a skill as failed to deprioritize it over time."""
        safe_name = self._get_safe_name(task_description)
        file_path = os.path.join(_SKILLS_DIR, f"{safe_name}.json")
        
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    skill = json.load(f)
                skill["fail_count"] += 1
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(skill, f, indent=4)
                logger.debug("Marked skill '%s' as failed.", safe_name)
            except Exception as e:
                logger.error("Failed to mark skill failure: %s", e)

    def get_skill_plan(self, task_description: str) -> Optional[str]:
        """Look for a matching skill with a high success rate."""
        task_lower = task_description.lower()
        
        best_match = None
        best_success_rate = -1.0
        
        try:
            for fname in os.listdir(_SKILLS_DIR):
                if not fname.endswith(".json"):
                    continue
                    
                file_path = os.path.join(_SKILLS_DIR, fname)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        skill = json.load(f)
                    
                    # Check if the task description matches any trigger
                    matched = False
                    for trigger in skill.get("trigger_phrases", []):
                        # Simple substring match (could be upgraded to embeddings later)
                        if trigger in task_lower or task_lower in trigger:
                            matched = True
                            break
                            
                    if matched:
                        successes = skill.get("success_count", 0)
                        fails = skill.get("fail_count", 0)
                        total = successes + fails
                        rate = successes / total if total > 0 else 1.0
                        
                        # Only use skills with >= 50% success rate
                        if rate >= 0.5 and rate > best_success_rate:
                            best_match = skill.get("plan_json")
                            best_success_rate = rate
                except Exception as e:
                    logger.error("Error reading skill %s: %s", fname, e)
                    continue
        except Exception as e:
            logger.error("Error iterating skills directory: %s", e)
            
        if best_match:
            logger.info("Found matching skill with success rate %.0f%%", best_success_rate * 100)
            
        return best_match
