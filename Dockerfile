# ----------------------------
# Base image
# ----------------------------
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ----------------------------
# System deps incl. Node.js
# ----------------------------
RUN apt-get update && apt-get install -y curl git build-essential && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ----------------------------
# Python deps (layer-cached)
# ----------------------------
COPY requirements-render-simple.txt .
RUN pip install --upgrade pip && pip install -r requirements-render-simple.txt

# ----------------------------
# Frontend deps (layer-cached)
# ----------------------------
COPY my-chatbot/package*.json my-chatbot/
WORKDIR /app/my-chatbot
RUN npm ci || npm install

# ----------------------------
# Copy rest of source & build frontend
# ----------------------------
COPY . /app
WORKDIR /app/my-chatbot
RUN npm run build

# ----------------------------
# Final runtime - go back to root where server.py is
# ----------------------------
WORKDIR /app

# Use environment variable PORT for Render compatibility
CMD gunicorn server_minimal:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
