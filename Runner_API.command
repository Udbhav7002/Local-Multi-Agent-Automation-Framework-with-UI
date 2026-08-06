#!/usr/bin/env bash
# macOS Double-Click Runner for FastAPI Server
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"
exec ./start.sh --api
