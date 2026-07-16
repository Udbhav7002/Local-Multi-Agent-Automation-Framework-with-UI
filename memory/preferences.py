"""
User preferences tracking.
"""
import asyncio
import os
import json
from datetime import datetime
from typing import Dict, Any

from core.logger import setup_logger

logger = setup_logger("UserPreferences")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PREFS_FILE = os.path.join(_PROJECT_ROOT, "user_preferences.json")

class UserPreferences:
    """Tracks and saves user preferences and app usage habits."""
    def __init__(self) -> None:
        self.prefs: Dict[str, Any] = {
            "apps_used": {},
            "last_updated": ""
        }
        # Note: load() must now be awaited by the Orchestrator after initialization

    async def load(self) -> None:
        """Load preferences from disk asynchronously."""
        if os.path.exists(_PREFS_FILE):
            try:
                def read_file():
                    with open(_PREFS_FILE, "r", encoding="utf-8") as f:
                        return json.load(f)
                data = await asyncio.to_thread(read_file)
                self.prefs.update(data)
            except Exception as e:
                logger.error("Failed to load user preferences: %s", e)

    async def save(self) -> None:
        """Save preferences to disk asynchronously."""
        self.prefs["last_updated"] = datetime.now().isoformat()
        try:
            def write_file():
                with open(_PREFS_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.prefs, f, indent=4)
            await asyncio.to_thread(write_file)
        except Exception as e:
            logger.error("Failed to save user preferences: %s", e)

    async def log_app_usage(self, app_name: str) -> None:
        """Log that an application was used."""
        if not app_name or app_name.strip() == "":
            return
            
        if "apps_used" not in self.prefs:
            self.prefs["apps_used"] = {}
            
        apps_used: Dict[str, int] = self.prefs["apps_used"]  # type: ignore[assignment]
        count = apps_used.get(app_name, 0)
        apps_used[app_name] = count + 1
        await self.save()

    def get_context_string(self) -> str:
        """Get a string representation of preferences to inject into LLM prompts."""
        apps = self.prefs.get("apps_used", {})
        if not apps:
            return ""
        
        # Sort by usage count descending
        sorted_apps = sorted(apps.items(), key=lambda x: x[1], reverse=True)
        top_apps = [name for name, _ in sorted_apps[:3]]
        
        return f"User's most frequently used apps: {', '.join(top_apps)}."
