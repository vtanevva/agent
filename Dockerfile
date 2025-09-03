# ----------------------------
# Base image
# ----------------------------
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ----------------------------
# System deps incl. Node.js (more reliable method)
# ----------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get install -y --no-install-recommends build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && node --version \
    && npm --version

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

# Use environment variable PORT for Railway compatibility
# Support both server.py and server_minimal.py
CMD gunicorn server:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
