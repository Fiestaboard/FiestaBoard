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
    pip install --no-cache-dir fastapi uvicorn[standard] supervisor

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

# Copy supervisord configs for process supervision
COPY supervisord.conf /app/supervisord.conf
COPY supervisord-dev.conf /app/supervisord-dev.conf
RUN chown appuser:appuser /app/supervisord.conf /app/supervisord-dev.conf

USER appuser

# Expose single port
EXPOSE 3000

# Health check via nginx -> API
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3000/api/health || exit 1

CMD ["supervisord", "-c", "/app/supervisord.conf"]
