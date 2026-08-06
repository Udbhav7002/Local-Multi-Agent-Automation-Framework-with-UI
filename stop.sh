#!/usr/bin/env bash
# ==============================================================================
# 🛑 Local Multi-Agent Automation Framework - Smart Stopper
# ==============================================================================
# Gracefully terminates running background API servers or terminal sessions.
# Usage:
#   ./stop.sh
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

echo -e "${BOLD}🛑 Stopping Local Multi-Agent Automation Framework Services...${RESET}"

STOPPED=0

# 1. Stop background PID file if present
if [ -f ".api.pid" ]; then
    PID=$(cat .api.pid 2>/dev/null || echo "")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo -e "  ${YELLOW}⚡ Stopping background API Server (PID: $PID)...${RESET}"
        kill "$PID" 2>/dev/null || true
        sleep 1
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID" 2>/dev/null || true
        fi
        echo -e "  ${GREEN}✓ API Server stopped.${RESET}"
        STOPPED=1
    fi
    rm -f .api.pid
fi

# 2. Check for any orphaned uvicorn api:app processes from this directory
PIDS=$(pgrep -f "uvicorn api:app" 2>/dev/null || true)
for p in $PIDS; do
    if [ "$p" != "$$" ]; then
        echo -e "  ${YELLOW}⚡ Terminating orphaned uvicorn service (PID: $p)...${RESET}"
        kill "$p" 2>/dev/null || true
        STOPPED=1
    fi
done

if [ "$STOPPED" -eq 0 ]; then
    echo -e "  ${GREEN}✓ No running background services found. Everything is clean!${RESET}"
else
    echo -e "  ${GREEN}✓ All services cleanly stopped.${RESET}"
fi
