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
RUN apt-get update && apt-get install -y curl git build-essential bash && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ----------------------------
# Python deps (layer-cached)
# ----------------------------
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ----------------------------
# Copy application code
# ----------------------------
WORKDIR /app
COPY . .

# ----------------------------
# Build Expo web app (authoritative frontend served by Flask from /app/web-build)
# IMPORTANT: this must happen AFTER copying the repo, otherwise the later COPY overwrites the build output.
# ----------------------------
WORKDIR /app/my-chatbot-expo
RUN npm ci || npm install
RUN rm -rf /app/web-build && npm run build:web
RUN if [ ! -f "/app/web-build/index.html" ]; then \
    echo "ERROR: index.html not found in /app/web-build after Expo export!" && \
    ls -la /app/web-build/ 2>/dev/null || echo "web-build directory does not exist" && \
    exit 1; \
    else \
    echo "✓ Expo web build successful - index.html found"; \
    fi

# ----------------------------
# Make startup script executable (start.sh is now in /app/)
# ----------------------------
WORKDIR /app
RUN chmod +x start.sh

# ----------------------------
# Final runtime - use dynamic PORT from Railway
# ----------------------------
WORKDIR /app

# Railway sets PORT environment variable automatically
# The start.sh script will handle the PORT variable properly
CMD ["./start.sh"]
