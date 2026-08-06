"""
Skill library for caching and reusing successful action sequences.
"""
import os
import json
import re
import hashlib
import difflib
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from core.logger import setup_logger

logger = setup_logger("SkillLibrary")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKILLS_DIR = os.path.join(_PROJECT_ROOT, "skills")

SkillDict = Dict[str, Any]


class SkillLibrary:
    """Manages reusable skills generated from past successful plans."""
    
    def __init__(self, skills_dir: Optional[str] = None) -> None:
        self.skills_dir = str(skills_dir) if skills_dir is not None else _SKILLS_DIR
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir, exist_ok=True)
        self._cache: Dict[str, SkillDict] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Populates the in-memory cache from skill JSON files on disk for O(1) lookups."""
        self._cache.clear()
        if not os.path.exists(self.skills_dir):
            return
            
        try:
            for fname in os.listdir(self.skills_dir):
                if not fname.endswith(".json"):
                    continue
                file_path = os.path.join(self.skills_dir, fname)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        skill: SkillDict = json.load(f)
                    skill_id = skill.get("skill_id") or os.path.splitext(fname)[0]
                    self._cache[skill_id] = skill
                except Exception as e:
                    logger.error("Error loading skill %s: %s", fname, e)
        except Exception as e:
            logger.error("Error reading skills directory %s: %s", self.skills_dir, e)
            
        logger.debug("Loaded %d skills into memory cache.", len(self._cache))

    def _normalize_text(self, text: str) -> str:
        """Clean and normalize text for comparison."""
        if not text or not text.strip():
            return ""
        return re.sub(r'[^a-zA-Z0-9\s]', '', text.lower()).strip()

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """
        Computes semantic similarity score between two texts using
        Jaccard token similarity and difflib SequenceMatcher ratio.
        """
        t1 = self._normalize_text(text1)
        t2 = self._normalize_text(text2)
        if not t1 or not t2:
            return 0.0
        if t1 == t2:
            return 1.0
            
        # Token Jaccard similarity
        tokens1 = set(t1.split())
        tokens2 = set(t2.split())
        if not tokens1 or not tokens2:
            jaccard = 0.0
        else:
            intersection = tokens1.intersection(tokens2)
            union = tokens1.union(tokens2)
            jaccard = len(intersection) / len(union) if union else 0.0
            
        # difflib sequence matching
        seq_match = difflib.SequenceMatcher(None, t1, t2).ratio()
        
        # Substring boost: only if one text is contained in another AND length ratio >= 0.65
        # This prevents short substrings (e.g. 'open safari') from falsely matching
        # multi-step commands (e.g. 'open safari and search black myth wukong').
        len_ratio = min(len(t1), len(t2)) / max(len(t1), len(t2)) if max(len(t1), len(t2)) > 0 else 0.0
        if (t1 in t2 or t2 in t1) and len_ratio >= 0.65 and min(len(t1), len(t2)) >= 4:
            return max(0.85, jaccard, seq_match)

        return max(jaccard, seq_match)

    def _find_matching_skill(self, task_description: str, threshold: float = 0.70) -> Optional[Tuple[str, SkillDict, float]]:
        """
        Searches in-memory cache for a skill matching the task description.
        Returns tuple of (skill_id, skill_dict, similarity_score) if found.
        """
        if not task_description or not task_description.strip():
            return None

        best_skill_id: Optional[str] = None
        best_skill: Optional[SkillDict] = None
        best_score = -1.0
        
        task_lower = task_description.lower().strip()
        
        for skill_id, skill in self._cache.items():
            trigger_phrases: List[str] = skill.get("trigger_phrases", [])  # type: ignore[assignment]
            skill_score = 0.0
            for trigger in trigger_phrases:
                trig_lower = trigger.lower().strip()
                if task_lower == trig_lower:
                    skill_score = 1.0
                    break
                score = self._compute_similarity(task_description, trigger)
                if score > skill_score:
                    skill_score = score
                    
            if skill_score >= threshold and skill_score > best_score:
                best_score = skill_score
                best_skill_id = skill_id
                best_skill = skill

        if best_skill_id and best_skill:
            return (best_skill_id, best_skill, best_score)
        return None

    def _get_safe_name(self, text: str) -> str:
        """Generate a clean, unique filename from a task description."""
        clean = re.sub(r'[^a-zA-Z0-9_\s]', '', text.lower()).strip()
        words = clean.split()[:5]
        prefix = '_'.join(words) if words else 'skill'
        text_hash = hashlib.md5(text.lower().encode()).hexdigest()[:8]
        return f"{prefix}_{text_hash}"

    def save_skill(self, task_description: str, plan_json: str) -> None:
        """Saves a successful plan as a reusable skill, deduplicating via semantic matching."""
        if not task_description or not task_description.strip():
            return

        # Check for existing semantically similar skill
        match_result = self._find_matching_skill(task_description, threshold=0.70)
        
        if match_result:
            skill_id, skill, score = match_result
            logger.debug("Found existing matching skill '%s' (similarity: %.2f) for deduplication.", skill_id, score)
        else:
            skill_id = self._get_safe_name(task_description)
            skill = {
                "skill_id": skill_id,
                "trigger_phrases": [],
                "plan_json": plan_json,
                "success_count": 0,
                "fail_count": 0,
                "last_used": ""
            }

        # Update plan in case the new one is updated
        skill["plan_json"] = plan_json
        
        # Add trigger phrase if new
        task_lower = task_description.lower().strip()
        trigger_phrases: List[str] = skill.get("trigger_phrases", [])  # type: ignore[assignment]
        if task_lower not in trigger_phrases:
            trigger_phrases.append(task_lower)
        skill["trigger_phrases"] = trigger_phrases
        
        skill["success_count"] = int(skill.get("success_count", 0)) + 1
        skill["last_used"] = datetime.now().isoformat()
        
        # Update in-memory cache
        self._cache[skill_id] = skill

        # Persist to disk
        file_path = os.path.join(self.skills_dir, f"{skill_id}.json")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(skill, f, indent=4)
            logger.debug("Saved skill '%s' to library.", skill_id)
        except Exception as e:
            logger.error("Failed to save skill '%s': %s", skill_id, e)

    def mark_failure(self, task_description: str) -> None:
        """Mark a skill as failed to deprioritize it over time."""
        if not task_description or not task_description.strip():
            return

        match_result = self._find_matching_skill(task_description, threshold=0.70)
        if match_result:
            skill_id, skill, _ = match_result
        else:
            skill_id = self._get_safe_name(task_description)
            if skill_id in self._cache:
                skill = self._cache[skill_id]
            else:
                return

        skill["fail_count"] = int(skill.get("fail_count", 0)) + 1
        self._cache[skill_id] = skill
        
        file_path = os.path.join(self.skills_dir, f"{skill_id}.json")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(skill, f, indent=4)
            logger.debug("Marked skill '%s' as failed.", skill_id)
        except Exception as e:
            logger.error("Failed to mark skill failure: %s", e)

    def get_skill_plan(self, task_description: str) -> Optional[str]:
        """Look for a matching skill with a high success rate (O(1) disk I/O, using RAM cache)."""
        if not task_description or not task_description.strip() or not self._cache:
            return None

        best_match_plan = None
        best_rank_score = -1.0
        best_success_rate = -1.0
        
        task_lower = task_description.lower().strip()

        for skill_id, skill in self._cache.items():
            trigger_phrases: List[str] = skill.get("trigger_phrases", [])  # type: ignore[assignment]
            match_score = 0.0
            
            for trigger in trigger_phrases:
                trig_lower = trigger.lower().strip()
                if trig_lower == task_lower:
                    match_score = 1.0
                    break
                else:
                    score = self._compute_similarity(task_description, trigger)
                    if score > match_score:
                        match_score = score

            if match_score >= 0.70:
                successes = int(skill.get("success_count", 0))
                fails = int(skill.get("fail_count", 0))
                total = successes + fails
                rate = successes / total if total > 0 else 1.0
                
                # Only use skills with >= 50% success rate
                if rate >= 0.5:
                    rank_score = match_score * 0.6 + rate * 0.4
                    if rank_score > best_rank_score:
                        best_rank_score = rank_score
                        best_success_rate = rate
                        best_match_plan = skill.get("plan_json")

        if best_match_plan:
            logger.info("Found matching skill with success rate %.0f%%", best_success_rate * 100)
            
        return best_match_plan
