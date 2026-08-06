#!/usr/bin/env bash
# ==============================================================================
# 🚀 Local Multi-Agent Automation Framework - Smart Launcher
# ==============================================================================
# Usage:
#   ./start.sh             -> Start Interactive Terminal UI
#   ./start.sh --api       -> Start FastAPI Server on http://127.0.0.1:8000
#   ./start.sh --bg        -> Start FastAPI Server in background (.api.pid)
#   ./start.sh --check     -> Run dependencies & system health tests
#   ./start.sh --help      -> Show usage info
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Colors for terminal output
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

function print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "  ███████ ████████  █████  ██████  ████████ "
    echo "  ██         ██    ██   ██ ██   ██    ██    "
    echo "  ███████    ██    ███████ ██████     ██    "
    echo "       ██    ██    ██   ██ ██   ██    ██    "
    echo "  ███████    ██    ██   ██ ██   ██    ██    "
    echo -e "${RESET}"
    echo -e "  ${GREEN}●${RESET} ${BOLD}Local Multi-Agent Automation Framework${RESET}"
    echo -e "  ──────────────────────────────────────────\n"
}

function check_venv() {
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}⚡ Virtual environment not found. Creating 'venv'...${RESET}"
        python3 -m venv venv
        echo -e "${GREEN}✓ Created venv.${RESET}"
        source venv/bin/activate
        echo -e "${YELLOW}⚡ Installing dependencies from requirements.txt...${RESET}"
        pip install --upgrade pip -q
        pip install -r requirements.txt
        echo -e "${GREEN}✓ Dependencies installed.${RESET}\n"
    else
        source venv/bin/activate
    fi
}

function check_ollama() {
    if command -v curl &>/dev/null; then
        if curl -s "http://localhost:11434/api/tags" &>/dev/null; then
            echo -e "  ${GREEN}✓ Ollama is ONLINE${RESET} (http://localhost:11434)"
        else
            echo -e "  ${YELLOW}⚠ Ollama is not responding at http://localhost:11434${RESET}"
            echo -e "    Please ensure Ollama is running in the background."
        fi
    fi
}

MODE="cli"

for arg in "$@"; do
    case "$arg" in
        --api)
            MODE="api"
            ;;
        --bg)
            MODE="bg"
            ;;
        --check)
            MODE="check"
            ;;
        --help|-h)
            print_banner
            echo -e "${BOLD}USAGE:${RESET}"
            echo "  ./start.sh             Launch Interactive Terminal UI"
            echo "  ./start.sh --api       Launch FastAPI Server (foreground)"
            echo "  ./start.sh --bg        Launch FastAPI Server (background daemon)"
            echo "  ./start.sh --check     Run test suite and dependency checks"
            echo "  ./start.sh --help      Show this help message"
            echo ""
            echo -e "${BOLD}EXAMPLES:${RESET}"
            echo "  ./start.sh"
            echo "  ./start.sh --api"
            echo "  ./stop.sh              Stop any running background services"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $arg${RESET}"
            echo "Run ./start.sh --help for usage."
            exit 1
            ;;
    esac
done

print_banner
check_venv
check_ollama

case "$MODE" in
    cli)
        echo -e "  ${CYAN}⚡ Starting Interactive Terminal UI...${RESET}\n"
        exec venv/bin/python main.py
        ;;
    api)
        echo -e "  ${CYAN}⚡ Starting FastAPI Server on http://127.0.0.1:8000 ...${RESET}"
        echo -e "     API Key Header: ${BOLD}X-API-Key: local-dev-key${RESET}\n"
        exec venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000 --reload
        ;;
    bg)
        if [ -f ".api.pid" ] && kill -0 "$(cat .api.pid)" 2>/dev/null; then
            echo -e "  ${YELLOW}⚠ API Server is already running (PID: $(cat .api.pid)).${RESET}"
            echo -e "     Use ${BOLD}./stop.sh${RESET} to stop it first."
            exit 1
        fi
        echo -e "  ${CYAN}⚡ Launching FastAPI Server in background...${RESET}"
        nohup venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000 > api_server.log 2>&1 &
        PID=$!
        echo "$PID" > .api.pid
        echo -e "  ${GREEN}✓ API Server running in background with PID: ${PID}${RESET}"
        echo -e "     Logs available in: ${BOLD}api_server.log${RESET}"
        echo -e "     To stop: ${BOLD}./stop.sh${RESET}"
        ;;
    check)
        echo -e "  ${CYAN}⚡ Running Test Suite & Verification...${RESET}\n"
        venv/bin/python -m pytest tests/ -v
        ;;
esac
