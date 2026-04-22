#!/bin/bash
# Gunicorn entrypoint for the AI chat service (orchestrator). Run from repo root.

set -e
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

PORT="${AI_CHAT_PORT:-5055}"
echo "Starting AI chat service on port $PORT"

exec gunicorn 'backend.ai_app:app' --bind "0.0.0.0:$PORT" --workers 1 --timeout 300
