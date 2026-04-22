#!/bin/bash
# Startup script for Railway deployment (core backend Flask app).
# Run from repo root; working directory must be backend/ for imports.

set -e
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT/backend"

PORT="${PORT:-5000}"
echo "Starting backend on port $PORT"

exec gunicorn app:app --bind "0.0.0.0:$PORT" --workers 1 --timeout 120

