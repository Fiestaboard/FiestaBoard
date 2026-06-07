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
    # Skip if nginx.conf is a read-only bind mount (e.g. dev compose).
    if ! touch /etc/nginx/nginx.conf 2>/dev/null; then
        echo "[entrypoint] /etc/nginx/nginx.conf is read-only; skipping nginx config setup."
        return 0
    fi

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

# ---------------------------------------------------------------------------
# Frame-embedding headers
# ---------------------------------------------------------------------------
# nginx.conf / nginx.https.conf / nginx-dev.conf each `include` the snippets
# directory inside their `server` block; this function renders the actual
# `add_header` lines into /etc/nginx/fiestaboard/frame-headers.conf so they can
# be controlled by env without baking a value into the image.
#
# Env vars (both optional):
#   FIESTABOARD_X_FRAME_OPTIONS  Defaults to "SAMEORIGIN" (historical
#                                behavior).  Common values: SAMEORIGIN, DENY.
#                                Special value "OFF" omits the header entirely
#                                so a CSP `frame-ancestors` directive can
#                                fully control framing in modern browsers.
#   FIESTABOARD_FRAME_ANCESTORS  Optional CSP `frame-ancestors` value.  When
#                                set, emits `Content-Security-Policy:
#                                frame-ancestors <value>`.  Example values:
#                                "'self'", "'self' https://my.host", "*".
#
# Defaults preserve the previous hard-coded `X-Frame-Options: SAMEORIGIN`
# for any deployment that doesn't set the new vars.  When the host has
# /etc/nginx bind-mounted read-only (e.g. some dev compose setups), we
# skip silently and fall back to whatever the mounted config provides.
configure_frame_headers() {
    SNIPPET_DIR=/etc/nginx/fiestaboard
    SNIPPET=$SNIPPET_DIR/frame-headers.conf

    if ! mkdir -p "$SNIPPET_DIR" 2>/dev/null; then
        echo "[entrypoint] cannot create $SNIPPET_DIR; using built-in defaults" >&2
        return 0
    fi
    if ! touch "$SNIPPET" 2>/dev/null; then
        echo "[entrypoint] $SNIPPET is read-only; skipping frame-header setup" >&2
        return 0
    fi

    XFO="${FIESTABOARD_X_FRAME_OPTIONS-SAMEORIGIN}"

    : > "$SNIPPET"
    if [ -n "$XFO" ] && [ "$XFO" != "OFF" ]; then
        printf 'add_header X-Frame-Options "%s" always;\n' "$XFO" >> "$SNIPPET"
    fi
    if [ -n "${FIESTABOARD_FRAME_ANCESTORS:-}" ]; then
        printf 'add_header Content-Security-Policy "frame-ancestors %s" always;\n' \
            "$FIESTABOARD_FRAME_ANCESTORS" >> "$SNIPPET"
    fi
}

# ---------------------------------------------------------------------------
# Reverse-proxy base-path rewriting (e.g. Home Assistant Ingress)
# ---------------------------------------------------------------------------
# Some embedding contexts (HA Supervisor Ingress, Traefik subpath routing)
# mount FiestaBoard under a per-installation URL prefix and signal that
# prefix to the upstream via an `X-Ingress-Path` request header.
#
# Post-migration to React Router v7 (Vite SPA), the UI emits relative
# asset URLs (`<script src="./assets/...">`) thanks to Vite's `base: "./"`
# config. The browser resolves those against `<base href>` in the
# document <head>. When FIESTABOARD_INGRESS_PATH_REWRITE=true, this
# snippet injects exactly one rule: `<base href="$http_x_ingress_path/">`.
# nginx fills in the value from the request header at proxy time.
#
# That is the entire HA Ingress integration. No sub_filter of asset
# URLs, no runtime prototype patching of HTMLLinkElement / fetch /
# XMLHttpRequest, no fight with React 19's hydration internals. The
# old four-fix chain (PRs #913, #914, #915, #918) collapses to one
# nginx line.
#
# Direct deployments: when X-Ingress-Path is absent the variable
# expands to "", giving `<base href="/">` — identity, no behavioral
# change. Even with the snippet enabled, standalone Docker / the
# public preview site keep working unchanged.
configure_ingress_path_rewrite() {
    SNIPPET_DIR=/etc/nginx/fiestaboard/location-root
    SNIPPET=$SNIPPET_DIR/base-path-rewrite.conf

    if ! mkdir -p "$SNIPPET_DIR" 2>/dev/null; then
        echo "[entrypoint] cannot create $SNIPPET_DIR; skipping base-path rewrite" >&2
        return 0
    fi

    # Default OFF -- only enabled when the operator opts in. This keeps
    # direct deployments on the zero-overhead path.
    case "${FIESTABOARD_INGRESS_PATH_REWRITE:-false}" in
        true|TRUE|1|yes|YES)
            ;;
        *)
            # Clear any stale snippet from a previous boot so the include
            # is a no-op next time nginx starts.
            if [ -f "$SNIPPET" ] && ! rm -f "$SNIPPET" 2>/dev/null; then
                echo "[entrypoint] cannot remove stale $SNIPPET; nginx will keep prior behavior" >&2
            fi
            return 0
            ;;
    esac

    if ! touch "$SNIPPET" 2>/dev/null; then
        echo "[entrypoint] $SNIPPET is read-only; skipping base-path rewrite" >&2
        return 0
    fi

    # Use a quoted heredoc so `$http_x_ingress_path` is preserved
    # verbatim for nginx to expand at request time (instead of being
    # interpolated by the shell at config-render time).
    cat > "$SNIPPET" <<'NGINX'
# Strip upstream gzip so sub_filter can see the response body.
# (nginx's outer `gzip on` re-compresses the rewritten response
# before it leaves the box, so the wire-level bytes are still small.)
proxy_set_header Accept-Encoding "";
sub_filter_once on;
# Inject <base href> into the HTML shell. Vite emits `<script src="./...">`
# and `<link href="./..."> ` (relative URLs) thanks to `base: "./"` in
# vite.config.ts, so the browser uses <base> to resolve them against
# the Ingress prefix. Dynamic ESM imports also honor <base href> via
# `import.meta.url`. This single rule replaces the runtime
# prototype-patching that broke React 19 hydration.
sub_filter '<head>' '<head><base href="$http_x_ingress_path/">';
NGINX
}

# Run cert/config setup before dropping privileges so the entrypoint can
# both write /etc/nginx/nginx.conf (root-owned) and chown cert files.
configure_frame_headers
configure_ingress_path_rewrite
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

# Fix ownership of bind-mounted web directory for dev mode (Vite's
# build dir lives at /app/web/build/ post-migration; in dev it isn't
# created — Vite serves from memory — but we chown both paths so a
# stale Next.js .next directory left over from before the cutover
# doesn't keep root-owned permissions after pulling the new image).
if [ -d /app/web/src ]; then
    chown -R appuser:appuser /app/web/build 2>/dev/null || true
    chown -R appuser:appuser /app/web/.react-router 2>/dev/null || true
fi

# Drop to the unprivileged application user and exec the CMD
exec gosu appuser "$@"
