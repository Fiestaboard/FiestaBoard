#!/bin/sh
set -e

# Ensure data and log directories exist and are owned by the app user.
# This handles bind-mounted host directories that may be owned by root (common on Linux).
mkdir -p /app/data/logs
chown -R appuser:appuser /app/data 2>/dev/null || true

# Ensure external_plugins directory exists and is writable for marketplace installs.
mkdir -p /app/external_plugins
chown appuser:appuser /app/external_plugins 2>/dev/null || true

# ---------------------------------------------------------------------------
# Self-update sidecar bearer token
# ---------------------------------------------------------------------------
# When `fiestaupdater` is enabled (COMPOSE_PROFILES=fiestaupdater), both this
# container and the sidecar must share a bearer token via the
# FIESTAUPDATER_TOKEN env var.  If the operator hasn't set one, we lazily
# generate a 256-bit hex token to data/.fiestaupdater-token and export it for
# the application process.  The compose service references the same file so
# both containers see the same value.
TOKEN_FILE=/app/data/.fiestaupdater-token
if [ -z "${FIESTAUPDATER_TOKEN:-}" ]; then
    if [ ! -f "$TOKEN_FILE" ]; then
        # 32 bytes -> 64 hex chars.  /dev/urandom is fine for this purpose
        # (sidecar compares via sha256, and the token never leaves the
        # internal docker network).
        head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$TOKEN_FILE"
        chmod 600 "$TOKEN_FILE"
        chown appuser:appuser "$TOKEN_FILE" 2>/dev/null || true
    fi
    FIESTAUPDATER_TOKEN="$(cat "$TOKEN_FILE")"
    export FIESTAUPDATER_TOKEN
fi

# ---------------------------------------------------------------------------
# HTTPS (Beta) -- swap nginx config and (re)generate cert when enabled.
# ---------------------------------------------------------------------------
# The user toggles this from Settings → Beta in the web UI, which writes
# `beta.https_enabled` into data/settings.json. We resolve that flag here,
# at container start, because nginx only reads its config once.
#
# When enabled:
#   * Generate a self-signed cert into data/certs/ if missing.
#   * Install /app/nginx.https.conf as /etc/nginx/nginx.conf.
# When disabled (or no cert files present):
#   * Install /app/nginx.http.conf as /etc/nginx/nginx.conf.
configure_https() {
    HTTPS_ENABLED=$(python -c '
import json, sys
try:
    with open("/app/data/settings.json", "r") as f:
        data = json.load(f)
    print("true" if bool(data.get("beta", {}).get("https_enabled")) else "false")
except (FileNotFoundError, json.JSONDecodeError, OSError):
    print("false")
' 2>/dev/null || echo "false")

    if [ "$HTTPS_ENABLED" = "true" ]; then
        echo "[entrypoint] HTTPS (Beta) is enabled; ensuring certificate exists."
        # Generate cert as appuser so the running services can read it.
        if [ "$(id -u)" = "0" ]; then
            gosu appuser python -m src.system.https_certs_cli ensure || {
                echo "[entrypoint] Cert generation failed; falling back to HTTP." >&2
                cp /app/nginx.http.conf /etc/nginx/nginx.conf
                return 0
            }
        else
            python -m src.system.https_certs_cli ensure || {
                echo "[entrypoint] Cert generation failed; falling back to HTTP." >&2
                cp /app/nginx.http.conf /etc/nginx/nginx.conf
                return 0
            }
        fi

        if [ -f /app/data/certs/fiestaboard.crt ] && [ -f /app/data/certs/fiestaboard.key ]; then
            cp /app/nginx.https.conf /etc/nginx/nginx.conf
            echo "[entrypoint] nginx will serve HTTPS on port 3000."
        else
            echo "[entrypoint] Cert files missing after generation; serving HTTP." >&2
            cp /app/nginx.http.conf /etc/nginx/nginx.conf
        fi
    else
        cp /app/nginx.http.conf /etc/nginx/nginx.conf
    fi
}

# Run cert/config setup before dropping privileges so the entrypoint can
# both write /etc/nginx/nginx.conf (root-owned) and chown cert files.
configure_https

# ---------------------------------------------------------------------------
# If the container is already running as a non-root user (e.g. Docker
# rootless mode, --user flag, or Kubernetes security contexts), skip all
# privilege operations and just exec the CMD directly.
# ---------------------------------------------------------------------------
if [ "$(id -u)" != "0" ]; then
    exec "$@"
fi

# ---------------------------------------------------------------------------
# Docker-socket permission fixup
# ---------------------------------------------------------------------------
# When /var/run/docker.sock is bind-mounted from the host the owning GID
# inside the container usually does not match any group that 'appuser'
# belongs to.  We detect the socket's GID, ensure a matching group exists
# inside the container, and add appuser to it so the Python Docker SDK can
# communicate with the daemon.
# ---------------------------------------------------------------------------
if [ -S /var/run/docker.sock ]; then
    DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)

    # Re-use an existing group that already owns the socket, or create one
    EXISTING_GROUP=$(getent group "$DOCKER_GID" | cut -d: -f1 || true)
    if [ -z "$EXISTING_GROUP" ]; then
        groupadd -g "$DOCKER_GID" dockersock 2>/dev/null || true
        DOCKER_GROUP="dockersock"
    else
        DOCKER_GROUP="$EXISTING_GROUP"
    fi

    usermod -aG "$DOCKER_GROUP" appuser 2>/dev/null || true
fi

# Fix ownership of bind-mounted web directory for dev mode
if [ -d /app/web/src ]; then
    chown -R appuser:appuser /app/web/.next 2>/dev/null || true
fi

# Drop to the unprivileged application user and exec the CMD
exec gosu appuser "$@"
