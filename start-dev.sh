#!/bin/sh
# Dev startup. Installs the web UI deps (RR7 + Vite + the rest) into
# the bind-mounted /app/web/node_modules volume, then hands off to
# supervisord which runs the API (uvicorn --reload), the Vite/RR7 dev
# server (HMR via WebSocket), and nginx.
#
# We need a Node toolchain in the dev container even though production
# doesn't ship one — Vite's dev server is a Node process. Production
# only serves the static build.
# @fiestaboard/ui installs from the GitHub Packages npm registry, which needs
# auth even for public packages. The image build receives the token as a
# BuildKit secret, but this runtime `npm install` does not, so materialize the
# token (passed through as NPM_TOKEN in docker-compose.dev.yml) into the user
# npmrc. Without this the install fails with "401 Unauthorized ... not provided".
if [ -n "${NPM_TOKEN:-}" ]; then
    echo "//npm.pkg.github.com/:_authToken=${NPM_TOKEN}" > "$HOME/.npmrc"
else
    echo "WARNING: NPM_TOKEN is not set — @fiestaboard/ui install will fail with 401."
    echo "         Run 'export NPM_TOKEN=\$(gh auth token)' on the host, then rebuild."
fi

echo "Installing web dependencies (this can take a minute on a cold container)..."
cd /app/web
# Wipe any stale node_modules from a previous image. The bind-mounted
# /app/web layout means a host-side rm doesn't reach the named volume,
# so we do it here on container start. Single-level traversal only —
# the named volume itself stays in place.
find node_modules -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
npm install --legacy-peer-deps --no-package-lock --no-audit 2>&1 | tail -10
cd /app

# Dev startup: supervisord manages API (with --reload), the Vite/RR7
# dev server, and nginx (proxying / to the dev server).
exec supervisord -c /app/supervisord-dev.conf
