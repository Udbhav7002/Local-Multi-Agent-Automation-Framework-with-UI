#!/usr/bin/env bash

# Find the directory where this Runner file is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Activate the local Python virtual environment
source venv/bin/activate

# Start the Multi-Agent Framework API Server
echo "Starting FastAPI Server on http://127.0.0.1:8000"
echo "Use X-API-Key: local-dev-key"
venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000
