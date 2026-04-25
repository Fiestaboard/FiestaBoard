#!/bin/bash
# =============================================================================
# FiestaUpdater entrypoint — starts a per-connection HTTP listener via socat
# that dispatches each connection to handler.sh.
# =============================================================================
set -eu

PORT="${FIESTAUPDATER_PORT:-8765}"

# Sanity-check required env at boot.
if [ -z "${FIESTAUPDATER_TOKEN:-}" ]; then
    echo "[fiestaupdater] FATAL: FIESTAUPDATER_TOKEN is not set" >&2
    echo "[fiestaupdater] Refusing to start without an auth token." >&2
    exit 1
fi

if [ ! -S /var/run/docker.sock ]; then
    echo "[fiestaupdater] WARNING: /var/run/docker.sock is not mounted." >&2
    echo "[fiestaupdater] The sidecar will start, but updates will fail." >&2
fi

if [ ! -f "${FIESTAUPDATER_COMPOSE_FILE}" ]; then
    echo "[fiestaupdater] WARNING: compose file not found at ${FIESTAUPDATER_COMPOSE_FILE}" >&2
fi

echo "[fiestaupdater] Starting on port ${PORT} (service=${FIESTAUPDATER_SERVICE})"

# socat invokes handler.sh once per accepted connection.
# - TCP-LISTEN:fork  → spawn a child per connection so requests don't block each other
# - reuseaddr        → fast restart
# - SYSTEM:          → run a shell command, wiring stdin/stdout to the socket
# Environment is inherited by the child (FIESTAUPDATER_TOKEN, etc.).
exec socat -T 30 \
    "TCP-LISTEN:${PORT},reuseaddr,fork" \
    "SYSTEM:/app/handler.sh"
