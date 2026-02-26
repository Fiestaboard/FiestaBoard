# Development container for GitHub Codespaces and VS Code Dev Containers
# Mirrors the production runtime (Python 3.14 + Node.js 22 + nginx) without
# multi-stage build overhead so the container starts quickly.

FROM python:3.14-slim

# Install system dependencies: Node.js, nginx, and build tools for native modules
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    git \
    make \
    nginx \
    procps \
    sudo \
    wget \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create nginx directories (matches production Dockerfile)
RUN mkdir -p /var/log/nginx /var/lib/nginx/tmp /run/nginx /var/lib/nginx/body
