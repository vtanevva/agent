#!/bin/bash
# Startup script for Railway deployment.
# Runs BOTH services in one container (Option A):
#   - AI chat service (ai_app) in background on AI_CHAT_PORT (default 5055)
#   - Core backend (core_app) in foreground on $PORT (Railway-provided)
# The core service talks to AI over http://127.0.0.1:${AI_CHAT_PORT}
# (matches DEFAULT_AI_URL in backend/services/ai_chat_client.py).

set -e
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

PORT="${PORT:-5000}"
AI_CHAT_PORT="${AI_CHAT_PORT:-5055}"
export AI_CHAT_PORT
# If caller didn't set AI_SERVICE_URL, point core at the in-container AI service.
export AI_SERVICE_URL="${AI_SERVICE_URL:-http://127.0.0.1:${AI_CHAT_PORT}}"

echo "Starting AI chat service on port $AI_CHAT_PORT (background)"
(
  cd "$REPO_ROOT"
  exec gunicorn 'backend.ai_app:app' \
    --bind "0.0.0.0:$AI_CHAT_PORT" \
    --workers 1 \
    --timeout 300
) &
AI_PID=$!

# If AI exits, bring the whole container down so Railway restarts cleanly.
trap 'echo "Shutting down (received signal)"; kill -TERM $AI_PID 2>/dev/null || true; wait $AI_PID 2>/dev/null || true; exit 0' TERM INT

cd "$REPO_ROOT/backend"
echo "Starting core backend on port $PORT (AI_SERVICE_URL=$AI_SERVICE_URL)"
gunicorn core_app:app --bind "0.0.0.0:$PORT" --workers 1 --timeout 120 &
CORE_PID=$!

# Wait on whichever exits first; propagate its status.
wait -n "$AI_PID" "$CORE_PID"
STATUS=$?
echo "A service exited with status $STATUS; stopping the other."
kill -TERM "$AI_PID" "$CORE_PID" 2>/dev/null || true
wait "$AI_PID" 2>/dev/null || true
wait "$CORE_PID" 2>/dev/null || true
exit "$STATUS"
