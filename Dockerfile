# ============================================================
# FiestaBoard Unified Dockerfile
# Combines API (Python/FastAPI) and UI (React Router v7 / Vite SPA)
# in one image. nginx serves the static UI bundle directly — no Node
# runtime process in production.
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

# --- Stage 2: Build the React Router v7 UI (static SPA) ---
FROM node:26-alpine AS ui-builder

ARG VERSION=dev

WORKDIR /app

# Build deps for native modules (lightningcss, swc, sharp if any)
RUN apk add --no-cache python3 make g++

# Install web dependencies. We use `npm install` (not `npm ci`) because
# this migration PR drops the Next.js-pinned package-lock.json — the
# first successful build in CI will produce a fresh lockfile that can
# be committed in a follow-up to restore reproducible `npm ci` builds.
# The lockfile is COPYed conditionally so the build works whether or
# not it has been committed yet.
COPY web/package.json ./
COPY web/package-lock.json* ./

RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then \
        npm ci --legacy-peer-deps --no-audit; \
    else \
        npm install --legacy-peer-deps --no-audit; \
    fi

# Copy source files (everything Vite + RR7 needs to build)
COPY web/ ./

# Static SPA build. Output lands in /app/build/client/ (RR7 framework
# mode with `ssr: false`). Cache the Vite build cache so local
# rebuilds are faster; CI doesn't benefit (fresh runner each job).
ENV NODE_OPTIONS="--max-old-space-size=4096"
RUN --mount=type=cache,target=/app/node_modules/.vite \
    npm run build

# --- Stage 3: Shared runtime base (API + static UI + nginx) ---
# This stage holds everything common to production and dev. The concrete
# `runtime` (production) and `runtime-dev` stages below both build FROM it.
FROM python:3.14-slim AS runtime-base

ARG VERSION=dev
ENV VERSION=${VERSION}

LABEL org.opencontainers.image.title="FiestaBoard" \
      org.opencontainers.image.description="Open-source self-hosted platform for controlling split-flap displays" \
      org.opencontainers.image.url="https://hub.docker.com/r/fiestaboard/fiestaboard" \
      org.opencontainers.image.documentation="https://fiestaboard.app" \
      org.opencontainers.image.source="https://github.com/Fiestaboard/FiestaBoard" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="FiestaBoard"

WORKDIR /app

# Install nginx, wget, git, and gosu. Node.js is no longer installed
# in the production runtime — the UI is a static Vite bundle that
# nginx serves directly. Dropping nodejs shrinks the runtime image
# by ~150MB.
# git is required for the external plugin install/update system.
# network-manager (nmcli + nm-online) is used by FiestaPi WiFi-management
# endpoints. Harmless on non-Pi deployments.
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    gosu \
    network-manager \
    nginx \
    openssl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=python-builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin

# Copy application code (API)
COPY src/ ./src/
COPY plugins/ ./plugins/
COPY tests/ ./tests/
COPY staff-picks/ ./staff-picks/
COPY plugin-registry.json ./plugin-registry.json

# Copy the static SPA bundle. Vite emits /app/build/client/ with
# index.html + hashed assets/ subdirectory. nginx serves this directly
# (see nginx.conf::location /).
COPY --from=ui-builder /app/build/client /app/web/build/client
COPY --from=ui-builder /app/public /app/web/public

# Copy nginx configuration (default HTTP) and the alternate HTTPS template.
COPY nginx.conf /etc/nginx/nginx.conf
COPY nginx.conf /app/nginx.http.conf
COPY nginx.https.conf /app/nginx.https.conf

# Copy "please wait" static page served by nginx while the API is starting up
RUN mkdir -p /app/static
COPY starting.html /app/static/starting.html

# Create nginx directories and set permissions
# /etc/nginx/fiestaboard is our dedicated snippet dir (avoids Debian's /etc/nginx/snippets/).
RUN mkdir -p /var/log/nginx /var/lib/nginx/tmp /run/nginx /var/lib/nginx/body /etc/nginx/fiestaboard

# Create data directory for logs and app state
RUN mkdir -p /app/data/logs

# Copy supervisord configs and entrypoint before creating user
COPY supervisord.conf /app/supervisord.conf
COPY supervisord-dev.conf /app/supervisord-dev.conf
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Prepare supervisord include directory
RUN mkdir -p /app/conf.d

# Create non-root user for security and transfer ownership
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /var/log/nginx /var/lib/nginx /run/nginx /etc/nginx

# Declare persistent data volume so Docker always creates a volume for /app/data,
# even when the container is run without an explicit -v mount.
VOLUME /app/data

# Expose single port
EXPOSE 3000

# Health check via nginx -> API
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3000/api/health || exit 1

# The entrypoint runs as root to fix Docker socket permissions,
# then drops to appuser via gosu before executing the CMD.
ENTRYPOINT ["/app/entrypoint.sh"]

# --- Stage 4 (optional): Dev runtime, only built when target=runtime-dev ---
# The Vite/React-Router dev server needs Node at runtime; production
# doesn't (nginx serves the static SPA). Split that into a separate
# target so the prod image keeps the ~150MB Node savings while
# docker-compose.dev.yml can opt in with `target: runtime-dev`.
#
# This stage is deliberately placed BEFORE the production `runtime` stage
# so that `runtime` remains the Dockerfile's LAST stage. A `docker build`
# without an explicit `--target` builds the last stage; keeping production
# last means the published image (and any target-less build) boots
# supervisord.conf, not supervisord-dev.conf. See issue #1377.
FROM runtime-base AS runtime-dev

USER root

# Pull the same Node 26.x that the ui-builder stage used so dev and
# build resolve packages the same way. `--with-deps` is implicit via
# the nodesource setup script.
RUN curl -fsSL https://deb.nodesource.com/setup_26.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && chown -R appuser:appuser /app

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["supervisord", "-c", "/app/supervisord-dev.conf"]

# --- Stage 5: Production runtime (DEFAULT target) ---
# Kept as the LAST stage on purpose. Because a target-less `docker build`
# resolves to the final stage, this guarantees the published image and CI
# builds that omit `--target` land on production (api + nginx via
# supervisord.conf) rather than the dev stage above. See issue #1377.
FROM runtime-base AS runtime

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["supervisord", "-c", "/app/supervisord.conf"]
