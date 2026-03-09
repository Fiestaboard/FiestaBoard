#!/bin/sh
set -e

# ---------------------------------------------------------------------------
# Enable in-container monitoring (Prometheus + Grafana) when requested.
# Copies the supervisord snippet into conf.d/ so that supervisord picks
# up the extra programs.  This runs before the root/non-root branching
# so it works regardless of the user the container runs as.
# ---------------------------------------------------------------------------
setup_monitoring() {
    mkdir -p /app/conf.d /app/data/grafana /app/data/prometheus
    LOCAL_MON=$(echo "${LOCAL_MONITORING:-false}" | tr '[:upper:]' '[:lower:]')
    if [ "$LOCAL_MON" = "true" ] || [ "$LOCAL_MON" = "1" ] || [ "$LOCAL_MON" = "yes" ]; then
        cp /app/supervisord-monitoring.conf /app/conf.d/monitoring.conf
    else
        rm -f /app/conf.d/monitoring.conf
    fi
}

setup_monitoring

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
