#!/bin/sh
# Install web UI dependencies for hot-reload dev server
echo "Installing web dependencies..."
cd /app/web
find node_modules -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
npm install --legacy-peer-deps --no-package-lock --no-audit 2>&1 | tail -5
cd /app

# Dev startup: supervisord manages API (with --reload), Next.js dev server, and nginx
exec supervisord -c /app/supervisord-dev.conf
