# ============================================================
# FiestaBoard Unified Dockerfile
# Combines API (Python/FastAPI) and UI (Next.js) in one image
# ============================================================

# --- Stage 1: Build Python dependencies ---
FROM python:3.14-slim AS python-builder

WORKDIR /app

# Install build dependencies for compiling Python packages with C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir fastapi uvicorn[standard]

# --- Stage 2: Build Next.js UI ---
FROM node:25-alpine AS ui-builder

ARG VERSION=dev

WORKDIR /app

# Install build dependencies for native modules (lightningcss, swc)
RUN apk add --no-cache python3 make g++

# Copy package files for dependency installation
COPY web/package.json ./

# Install ALL dependencies (needed for build)
RUN --mount=type=cache,target=/root/.npm \
    npm install --legacy-peer-deps --no-audit

# Copy source files
COPY web/ ./

# Build the Next.js app with standalone output
ENV NODE_OPTIONS="--max-old-space-size=4096"
RUN npm run build

# --- Stage 3: Final unified runtime image ---
FROM python:3.14-slim

ARG VERSION=dev
ENV VERSION=${VERSION}

WORKDIR /app

# Install Node.js, nginx, and wget
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nginx \
    wget \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=python-builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin

# Copy application code (API)
COPY src/ ./src/
COPY plugins/ ./plugins/
COPY tests/ ./tests/

# Copy Next.js standalone build from UI builder
COPY --from=ui-builder /app/.next/standalone ./web/
COPY --from=ui-builder /app/.next/static ./web/.next/static
COPY --from=ui-builder /app/public ./web/public

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Create nginx directories and set permissions
RUN mkdir -p /var/log/nginx /var/lib/nginx/tmp /run/nginx /var/lib/nginx/body

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /var/log/nginx /var/lib/nginx /run/nginx /etc/nginx

# Create startup script that runs API, Next.js, and nginx
RUN echo '#!/bin/sh' > /app/start.sh && \
    echo 'set -e' >> /app/start.sh && \
    echo '' >> /app/start.sh && \
    echo '# Start the API server in background' >> /app/start.sh && \
    echo 'echo "Starting API server on port 8000..."' >> /app/start.sh && \
    echo 'cd /app && python -m uvicorn src.api_server:app --host 127.0.0.1 --port 8000 &' >> /app/start.sh && \
    echo 'API_PID=$!' >> /app/start.sh && \
    echo '' >> /app/start.sh && \
    echo '# Start Next.js server in background' >> /app/start.sh && \
    echo 'echo "Starting Next.js server on port 3001..."' >> /app/start.sh && \
    echo 'cd /app/web && PORT=3001 HOSTNAME=127.0.0.1 node server.js &' >> /app/start.sh && \
    echo 'NEXTJS_PID=$!' >> /app/start.sh && \
    echo '' >> /app/start.sh && \
    echo '# Wait for services to start' >> /app/start.sh && \
    echo 'sleep 2' >> /app/start.sh && \
    echo '' >> /app/start.sh && \
    echo '# Start nginx in foreground' >> /app/start.sh && \
    echo 'echo "Starting nginx on port 3000..."' >> /app/start.sh && \
    echo 'nginx -g "daemon off;" &' >> /app/start.sh && \
    echo 'NGINX_PID=$!' >> /app/start.sh && \
    echo '' >> /app/start.sh && \
    echo '# Wait for any process to exit' >> /app/start.sh && \
    echo 'wait $API_PID $NEXTJS_PID $NGINX_PID' >> /app/start.sh && \
    chmod +x /app/start.sh && \
    chown appuser:appuser /app/start.sh

USER appuser

# Expose single port
EXPOSE 3000

# Health check via nginx
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["/bin/sh", "/app/start.sh"]
