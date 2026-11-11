"""
Memory module for storing and retrieving successful and failed plans using ChromaDB.
"""
import asyncio
import os
import uuid

import chromadb

from core.config import config
from core.logger import setup_logger

logger = setup_logger("ChromaStore")

# Resolve chroma_db relative to the project root, not os.getcwd()
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHROMA_DB_PATH = os.path.join(_PROJECT_ROOT, "chroma_db")


class ChromaStore:
    """
    Handles interactions with ChromaDB for semantic memory retrieval.
    Stores past execution plans and their success/failure states.

    WARNING: Task descriptions and plans are stored unencrypted in the local
    ChromaDB database. Do not include sensitive data (passwords, API keys, etc.)
    in task descriptions. The database is stored at: <project_root>/chroma_db/
    """
    def __init__(self) -> None:
        logger.info("ChromaStore initialized. Data stored unencrypted at: %s", _CHROMA_DB_PATH)
        # Initialize chromadb persistent client
        self.client = chromadb.PersistentClient(path=_CHROMA_DB_PATH)
        self.success_collection = self.client.get_or_create_collection(
            name="successful_plans")
        self.failure_collection = self.client.get_or_create_collection(
            name="failed_plans")
        self.episodes_collection = self.client.get_or_create_collection(
            name="episodes")

    def _sync_get_plan(self, task_description: str) -> str | None:
        try:
            results = self.success_collection.query(
                query_texts=[task_description],
                n_results=1
            )
            documents = results.get('documents')
            distances = results.get('distances')
            if documents and distances and len(documents[0]) > 0:
                distance = distances[0][0]
                if distance < config.memory_success_threshold:
                    logger.debug("Found cached plan with distance: %s", distance)
                    return str(documents[0][0])
            return None
        except (ValueError, OSError) as e:
            logger.error("Error querying success collection: %s", e)
            return None

    async def get_plan(self, task_description: str) -> str | None:
        """Query ChromaDB for an exact or highly similar task."""
        return await asyncio.to_thread(self._sync_get_plan, task_description)

    def _sync_save_plan(self, task_description: str, plan_json: str) -> None:
        try:
            doc_id = str(uuid.uuid4())
            self.success_collection.add(
                documents=[plan_json],
                metadatas=[{"task": task_description}],
                ids=[doc_id]
            )
            logger.debug("Successfully saved plan to ChromaStore with ID: %s", doc_id)
        except (ValueError, OSError) as e:
            logger.error("Error saving to success collection: %s", e)

    async def save_plan(self, task_description: str, plan_json: str) -> None:
        """Save a successful plan to ChromaDB using UUIDs."""
        await asyncio.to_thread(self._sync_save_plan, task_description, plan_json)

    def _sync_get_failures(self, task_description: str) -> list:
        try:
            results = self.failure_collection.query(
                query_texts=[task_description],
                n_results=3
            )
            documents = results.get('documents')
            distances = results.get('distances')
            metadatas = results.get('metadatas')
            failures = []
            if documents and distances and metadatas and len(documents) > 0:
                for idx, doc in enumerate(documents[0]):
                    distance = distances[0][idx]
                    if distance < config.memory_failure_threshold:
                        reason = metadatas[0][idx].get('reason', 'Unknown reason')
                        failures.append({'plan': doc, 'reason': reason})
            return failures
        except (ValueError, OSError) as e:
            logger.error("Error querying failure collection: %s", e)
            return []

    async def get_failures(self, task_description: str) -> list:
        """Get past failed strategies for a similar task."""
        return await asyncio.to_thread(self._sync_get_failures, task_description)

    def _sync_save_failure(self, task_description: str, failed_plan: str, reason: str) -> None:
        try:
            doc_id = str(uuid.uuid4())
            self.failure_collection.add(
                documents=[failed_plan],
                metadatas=[{"task": task_description, "reason": reason}],
                ids=[doc_id]
            )
            logger.info("Logged failed plan to Reflection Memory to prevent future recurrence.")
        except (ValueError, OSError) as e:
            logger.error("Error saving to failure collection: %s", e)

    async def save_failure(self, task_description: str, failed_plan: str, reason: str) -> None:
        """Save a failed plan to ChromaDB."""
        await asyncio.to_thread(self._sync_save_failure, task_description, failed_plan, reason)

    def _sync_save_episode(self, episode_data: dict) -> None:
        import json
        try:
            doc_id = str(uuid.uuid4())
            task = episode_data.get("task", "unknown_task")
            self.episodes_collection.add(
                documents=[json.dumps(episode_data)],
                metadatas=[{"task": task}],
                ids=[doc_id]
            )
            logger.debug("Saved episode trace to ChromaDB with ID: %s", doc_id)
        except Exception as e:
            logger.error("Error saving episode: %s", e)

    async def save_episode(self, episode_data: dict) -> None:
        """Store a complete execution trace (episode)."""
        await asyncio.to_thread(self._sync_save_episode, episode_data)

    def _sync_get_similar_episodes(self, task_description: str, limit: int = 3) -> list[dict]:
        import json
        try:
            results = self.episodes_collection.query(
                query_texts=[task_description],
                n_results=limit
            )
            episodes = []
            documents = results.get('documents')
            distances = results.get('distances')
            if documents and distances and len(documents) > 0:
                for idx, doc in enumerate(documents[0]):
                    distance = distances[0][idx]
                    if distance < config.memory_episode_threshold:
                        try:
                            ep_dict = json.loads(doc)
                            ep_dict["_distance"] = distance
                            episodes.append(ep_dict)
                        except Exception:
                            pass
            return episodes
        except (ValueError, OSError) as e:
            logger.error("Error querying episodes: %s", e)
            return []

    async def get_similar_episodes(self, task_description: str, limit: int = 3) -> list[dict]:
        """Retrieve similar past episodes."""
        return await asyncio.to_thread(self._sync_get_similar_episodes, task_description, limit)

    def _sync_summarize_old_episodes(self, max_episodes: int = 100) -> int:
        try:
            results = self.episodes_collection.get()
            if not results or not results.get('ids'):
                return 0

            ids = results['ids']
            if len(ids) <= max_episodes:
                return 0

            # Prune older episodes (insertion order)
            excess = len(ids) - max_episodes
            ids_to_delete = ids[:excess]

            self.episodes_collection.delete(ids=ids_to_delete)
            logger.info("Summarized/Pruned %d old episodes from ChromaDB to maintain speed.", len(ids_to_delete))
            return len(ids_to_delete)
        except Exception as e:
            logger.error("Error summarizing episodes: %s", e)
            return 0

    async def summarize_old_episodes(self, max_episodes: int = 100) -> int:
        """Run a background job to summarize and prune old episodic memories."""
        return await asyncio.to_thread(self._sync_summarize_old_episodes, max_episodes)

    async def close(self) -> None:
        """Gracefully release the ChromaDB connection."""
        try:
            logger.debug("Closing ChromaStore...")
            for attr in ("success_collection", "failure_collection", "episodes_collection", "client"):
                if hasattr(self, attr):
                    delattr(self, attr)
            logger.debug("ChromaStore closed successfully.")
        except Exception as e:
            logger.error("Error closing ChromaStore: %s", e)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
