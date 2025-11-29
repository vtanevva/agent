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
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ----------------------------
# Copy application code
# ----------------------------
COPY . /app

# ----------------------------
# Setup startup script
# ----------------------------
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# ----------------------------
# Final runtime - use dynamic PORT from Railway
# ----------------------------
WORKDIR /app

# Railway sets PORT environment variable automatically
# The start.sh script will handle the PORT variable properly
CMD ["/app/start.sh"]
