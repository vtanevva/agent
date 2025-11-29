#!/bin/bash
# Startup script for Railway deployment
# Handles PORT environment variable dynamically

PORT=${PORT:-10000}
echo "Starting server on port $PORT"

exec gunicorn server:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120

