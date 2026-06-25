from typing import Optional

class InMemoryStore:
    """
    Simple in-memory implementation of MemoryStore for testing.
    No persistence, no semantic search — just exact-match lookups.
    """

    def __init__(self) -> None:
        self._plans: dict[str, str] = {}
        self._failures: list[dict] = []
        self._episodes: list[dict] = []

    def get_plan(self, task_description: str) -> Optional[str]:
        return self._plans.get(task_description)

    def save_plan(self, task_description: str, plan_json: str) -> None:
        self._plans[task_description] = plan_json

    def get_failures(self, task_description: str) -> list:
        return [
            f for f in self._failures
            if task_description.lower() in f.get("task", "").lower()
        ]

    def save_failure(
        self, task_description: str, failed_plan: str, reason: str
    ) -> None:
        self._failures.append({
            "task": task_description,
            "plan": failed_plan,
            "reason": reason,
        })

    def save_episode(self, episode_data: dict) -> None:
        self._episodes.append(episode_data)

    def get_similar_episodes(self, task_description: str, limit: int = 3) -> list[dict]:
        return self._episodes[:limit]

    def close(self) -> None:
        pass
