"""
Memory module for storing and retrieving successful and failed plans using ChromaDB.
"""
import os
import uuid
from typing import Optional

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
    """
    def __init__(self) -> None:
        # Initialize chromadb persistent client
        self.client = chromadb.PersistentClient(path=_CHROMA_DB_PATH)
        self.success_collection = self.client.get_or_create_collection(
            name="successful_plans")
        self.failure_collection = self.client.get_or_create_collection(
            name="failed_plans")
        self.episodes_collection = self.client.get_or_create_collection(
            name="episodes")

    def get_plan(self, task_description: str) -> Optional[str]:
        """Query ChromaDB for an exact or highly similar task."""
        try:
            results = self.success_collection.query(
                query_texts=[task_description],
                n_results=1
            )
            if results and results.get('documents') and len(
                    results['documents'][0]) > 0:
                # Check distance to ensure high confidence
                distance = results['distances'][0][0]
                if distance < config.memory_success_threshold:
                    logger.debug(
                        "Found cached plan with distance: %s", distance)
                    return results['documents'][0][0]
            return None
        except (ValueError, OSError) as e:
            logger.error("Error querying success collection: %s", e)
            return None

    def save_plan(self, task_description: str, plan_json: str) -> None:
        """Save a successful plan to ChromaDB using UUIDs."""
        try:
            doc_id = str(uuid.uuid4())
            self.success_collection.add(
                documents=[plan_json],
                metadatas=[{"task": task_description}],
                ids=[doc_id]
            )
            logger.debug(
                "Successfully saved plan to ChromaStore with ID: %s", doc_id)
        except (ValueError, OSError) as e:
            logger.error("Error saving to success collection: %s", e)

    def get_failures(self, task_description: str) -> list:
        """Get past failed strategies for a similar task."""
        try:
            results = self.failure_collection.query(
                query_texts=[task_description],
                n_results=3
            )
            failures = []
            if results and results.get('documents') and len(
                    results['documents']) > 0:
                for idx, doc in enumerate(results['documents'][0]):
                    distance = results['distances'][0][idx]
                    if distance < config.memory_failure_threshold:
                        reason = results['metadatas'][0][idx].get(
                            'reason', 'Unknown reason')
                        failures.append({'plan': doc, 'reason': reason})
            return failures
        except (ValueError, OSError) as e:
            logger.error("Error querying failure collection: %s", e)
            return []

    def save_failure(
            self,
            task_description: str,
            failed_plan: str,
            reason: str) -> None:
        """Save a failed plan to ChromaDB."""
        try:
            doc_id = str(uuid.uuid4())
            self.failure_collection.add(
                documents=[failed_plan],
                metadatas=[{"task": task_description, "reason": reason}],
                ids=[doc_id]
            )
            logger.info(
                "Logged failed plan to Reflection Memory to prevent future recurrence.")
        except (ValueError, OSError) as e:
            logger.error("Error saving to failure collection: %s", e)

    def save_episode(self, episode_data: dict) -> None:
        """Store a complete execution trace (episode)."""
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

    def get_similar_episodes(self, task_description: str, limit: int = 3) -> list[dict]:
        """Retrieve similar past episodes."""
        import json
        try:
            results = self.episodes_collection.query(
                query_texts=[task_description],
                n_results=limit
            )
            episodes = []
            if results and results.get('documents') and len(results['documents']) > 0:
                for idx, doc in enumerate(results['documents'][0]):
                    distance = results['distances'][0][idx]
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

    def close(self) -> None:
        """Gracefully release the ChromaDB connection and flush to disk."""
        try:
            logger.debug("Closing ChromaStore and flushing to disk...")
            # PersistentClient doesn't strictly require closing, but clearing references 
            # helps trigger garbage collection of the SQLite connections.
            self.success_collection = None
            self.failure_collection = None
            self.episodes_collection = None
            self.client = None
        except Exception as e:
            logger.error("Error closing ChromaStore: %s", e)
