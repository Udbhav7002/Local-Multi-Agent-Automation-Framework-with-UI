---
name: Local API Routing
description: Interfacing natively with local FastAPI endpoints, databases, and managing hardware resources.
---

# Local API Routing Instructions

When you need to interact with the underlying database or fetch data from internal FastAPI endpoints on the local machine (e.g., retrieving jobs from `jobs.db` or hitting `localhost:8000/status`), DO NOT write a full Python script if a simple request will suffice.

## API Requests
Use the `curl` command to interact with local APIs via the `run_command` action.
Example: `curl -s -X GET http://localhost:8000/status/1234`

## Database Queries
To query local SQLite databases (like `jobs.db` or `chroma_db`), use the native `sqlite3` CLI tool.
Example: `sqlite3 jobs.db "SELECT * FROM jobs WHERE status='RUNNING';"`

This approach is significantly faster and less error-prone than generating boilerplate Python code.
