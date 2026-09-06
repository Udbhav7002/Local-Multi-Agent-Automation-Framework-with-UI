# ADR 0001: ChromaDB over Cloud Vector DBs

## Context
The Local Multi-Agent Automation Framework requires a semantic memory layer to store past failure states, successful execution plans, and episodic memory traces. Agents need to retrieve context dynamically using vector embeddings.

## Decision
We chose to use ChromaDB running locally rather than a cloud solution like Pinecone or Weaviate.

## Rationale
1. **Privacy-First**: The core philosophy of this framework is local execution. Using a cloud vector database would compromise user privacy by sending potentially sensitive OS execution context off-device.
2. **Zero Setup**: ChromaDB operates in-memory or via local SQLite-based persistence without requiring the user to run a separate Docker container for the database.
3. **Open-Weight Alignment**: By keeping the vector store local, it pairs perfectly with local LLMs (Ollama), ensuring the framework can function completely offline.

## Consequences
- Requires background jobs to prune episodic memory (as implemented in Phase 4) to prevent local storage bloat and slow retrieval times.
- Search latency is dependent on local disk speed rather than optimized cloud indexing.
