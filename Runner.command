#!/usr/bin/env bash

# Find the directory where this Runner file is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Activate the local Python virtual environment
source venv/bin/activate

# Start the Multi-Agent Framework
venv/bin/python main.py
