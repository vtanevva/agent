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
# Build Expo web app first (before copying everything)
# ----------------------------
COPY my-chatbot-expo/package*.json my-chatbot-expo/
WORKDIR /app/my-chatbot-expo
RUN npm ci || npm install

# Copy Expo app source
COPY my-chatbot-expo/ /app/my-chatbot-expo/

# Build Expo web app
# For Expo SDK 54, use: npx expo export --platform web
# Default output is 'dist' directory, we'll move it to web-build
RUN echo "Building Expo web app..." && \
    cd /app/my-chatbot-expo && \
    echo "Running Expo export for web platform..." && \
    npx expo export --platform web && \
    echo "Checking export output..." && \
    (if [ -d "dist" ]; then \
        echo "Found 'dist' directory, moving to web-build..." && \
        mv dist /app/web-build && \
        echo "✓ Moved dist to /app/web-build"; \
    elif [ -d "/app/my-chatbot-expo/dist" ]; then \
        echo "Found dist in my-chatbot-expo, moving..." && \
        mv /app/my-chatbot-expo/dist /app/web-build && \
        echo "✓ Moved to /app/web-build"; \
    else \
        echo "ERROR: dist directory not found after export!" && \
        echo "Listing current directory:" && ls -la && \
        exit 1; \
    fi) && \
    echo "Verifying web-build contents..." && \
    ls -la /app/web-build/ | head -20

# Verify build was successful
RUN if [ ! -f "/app/web-build/index.html" ]; then \
    echo "ERROR: index.html not found in web-build!" && \
    ls -la /app/web-build/ 2>/dev/null || echo "web-build directory does not exist" && \
    exit 1; \
    else \
    echo "✓ Expo web build successful - index.html found"; \
    fi

# ----------------------------
# Copy rest of application code
# ----------------------------
WORKDIR /app
COPY . .

# ----------------------------
# Make startup script executable (start.sh is now in /app/)
# ----------------------------
RUN chmod +x start.sh

# ----------------------------
# Final runtime - use dynamic PORT from Railway
# ----------------------------
WORKDIR /app

# Railway sets PORT environment variable automatically
# The start.sh script will handle the PORT variable properly
CMD ["./start.sh"]
