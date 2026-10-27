#!/bin/bash
# Memory Journey: start the read-only monitor.
# Usage:  ./run.sh [experiment-folder] [port]
#   ./run.sh                                         -> paper-eval-neo4j-gemini on http://127.0.0.1:8731
#   ./run.sh ~/mem0-repro/paper-eval-gemini 8732     -> the finished Kuzu run on http://127.0.0.1:8732
cd "$(dirname "$0")" || exit 1
FOLDER="${1:-$HOME/mem0-repro/paper-eval-neo4j-gemini}"
PORT="${2:-8731}"
exec .venv/bin/python server.py "$FOLDER" --port "$PORT"
