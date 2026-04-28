#!/bin/bash
# =============================================================================
# FiestaUpdater per-connection HTTP handler.
# Invoked by socat with stdin/stdout bound to the client socket.
#
# Routes:
#   GET  /healthz         → 200  {"status":"ok"}
#   GET  /version         → 200  {"image":"<repo:tag>","digest":"<sha256:...>"}
#   POST /update          → 202  {"status":"queued"}   (requires Bearer auth)
#
# Security notes:
#   - Authentication: shared bearer token from FIESTAUPDATER_TOKEN env.
#     Compared via SHA-256 hash to reduce timing-attack surface.
#   - The compose service name is read from env but additionally validated
#     against a strict allow-list pattern ([a-z0-9_-]+) before being passed
#     to `docker compose`.  No user input is ever interpolated into a shell
#     command.
#   - The listener is *not* published to the host (compose-network only).
# =============================================================================
set -u

PORT="${FIESTAUPDATER_PORT:-8765}"
COMPOSE_FILE="${FIESTAUPDATER_COMPOSE_FILE:-/compose/docker-compose.yml}"
SERVICE="${FIESTAUPDATER_SERVICE:-fiestaboard}"

# ---------------------------------------------------------------------------
# Allow-list: the service name we are willing to act on.  Even with a
# compromised env, a value like "fiestaboard;rm -rf /" is rejected here
# because we require a strict character class.
# ---------------------------------------------------------------------------
if ! printf '%s' "$SERVICE" | grep -qE '^[a-z0-9_-]+$'; then
    SERVICE="fiestaboard"
fi

log() {
    # Stderr so it shows up in `docker logs`, prefixed for grep-ability.
    printf '[fiestaupdater] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

# ---------------------------------------------------------------------------
# Tiny HTTP response writer.
# Args: <status_code> <reason_phrase> <body>
# ---------------------------------------------------------------------------
respond() {
    local code="$1"
    local reason="$2"
    local body="$3"
    local len
    len=${#body}
    printf 'HTTP/1.1 %s %s\r\n' "$code" "$reason"
    printf 'Content-Type: application/json\r\n'
    printf 'Content-Length: %s\r\n' "$len"
    printf 'Connection: close\r\n'
    printf 'X-FiestaUpdater: 1\r\n'
    printf '\r\n'
    printf '%s' "$body"
}

# ---------------------------------------------------------------------------
# Constant-time-ish bearer token check.
# We compare SHA-256 hashes of expected vs presented; the hash is fixed-length,
# which makes a string-compare side channel useless for recovering the token.
# ---------------------------------------------------------------------------
check_token() {
    local presented="$1"
    [ -n "$presented" ] || return 1
    [ -n "${FIESTAUPDATER_TOKEN:-}" ] || return 1
    local a b
    a=$(printf '%s' "$presented" | sha256sum | cut -d' ' -f1)
    b=$(printf '%s' "$FIESTAUPDATER_TOKEN" | sha256sum | cut -d' ' -f1)
    [ "$a" = "$b" ]
}

# ---------------------------------------------------------------------------
# Read request line + headers from stdin.
# Sets: REQ_METHOD, REQ_PATH, REQ_AUTH, REQ_CONTENT_LENGTH
# ---------------------------------------------------------------------------
parse_request() {
    REQ_METHOD=""; REQ_PATH=""; REQ_AUTH=""; REQ_CONTENT_LENGTH=0
    local line
    # Request line.
    if ! IFS=' ' read -r REQ_METHOD REQ_PATH _; then
        return 1
    fi
    # Strip trailing \r.
    REQ_METHOD="${REQ_METHOD%$'\r'}"
    REQ_PATH="${REQ_PATH%$'\r'}"
    # Strip query string if present (we don't use any).
    REQ_PATH="${REQ_PATH%%\?*}"
    # Headers.
    while IFS= read -r line; do
        line="${line%$'\r'}"
        [ -z "$line" ] && break
        # Lower-case the header name for comparison.
        local name="${line%%:*}"
        local value="${line#*:}"
        # Trim leading space from value.
        value="${value# }"
        case "$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')" in
            authorization)   REQ_AUTH="$value" ;;
            content-length)  REQ_CONTENT_LENGTH="$value" ;;
        esac
    done
    return 0
}

# ---------------------------------------------------------------------------
# GET /version — current digest of the running fiestaboard container.
# ---------------------------------------------------------------------------
handle_version() {
    local image digest
    image=$(docker inspect --format '{{.Config.Image}}' "$SERVICE" 2>/dev/null || echo "")
    digest=$(docker inspect --format '{{.Image}}' "$SERVICE" 2>/dev/null || echo "")
    respond 200 OK "{\"service\":\"${SERVICE}\",\"image\":\"${image}\",\"digest\":\"${digest}\"}"
}

# ---------------------------------------------------------------------------
# POST /update — pull the latest image and recreate the service.
# Returns 202 immediately; the actual `compose up -d` is run in the
# background because it will likely outlive the HTTP connection (the
# fiestaboard container, which made the request, is being torn down).
# ---------------------------------------------------------------------------
handle_update() {
    log "update requested for service=${SERVICE}"
    if [ ! -f "$COMPOSE_FILE" ]; then
        log "compose file missing at ${COMPOSE_FILE}"
        respond 500 "Internal Server Error" '{"error":"compose_file_missing"}'
        return
    fi
    # Capture the digest before so logs show the change.
    local before
    before=$(docker inspect --format '{{.Image}}' "$SERVICE" 2>/dev/null || echo "")
    log "pre-update digest=${before}"

    # Run the actual update detached so we can ack the client first.
    # We want the output to appear in `docker logs fiestaupdater`, which means
    # PID 1's stderr.  In a Linux container that's /proc/1/fd/2; on macOS (and
    # in tests) we fall back to /dev/null to avoid spamming the test runner.
    local logsink
    if [ -e /proc/1/fd/2 ]; then
        logsink=/proc/1/fd/2
    else
        logsink=/dev/null
    fi
    nohup bash -c "
        set -eu
        echo '[fiestaupdater] pulling latest image for ${SERVICE}...'
        docker compose -f '${COMPOSE_FILE}' pull '${SERVICE}'
        echo '[fiestaupdater] recreating ${SERVICE}...'
        docker compose -f '${COMPOSE_FILE}' up -d --no-deps '${SERVICE}'
        after=\$(docker inspect --format '{{.Image}}' '${SERVICE}' 2>/dev/null || echo '')
        echo \"[fiestaupdater] post-update digest=\${after}\"
    " >>"$logsink" 2>&1 &

    respond 202 Accepted "{\"status\":\"queued\",\"service\":\"${SERVICE}\",\"previous_digest\":\"${before}\"}"
}

# ---------------------------------------------------------------------------
# Main dispatch.
# ---------------------------------------------------------------------------
parse_request || { respond 400 "Bad Request" '{"error":"malformed_request"}'; exit 0; }

case "${REQ_METHOD} ${REQ_PATH}" in
    "GET /healthz")
        respond 200 OK '{"status":"ok"}'
        ;;
    "GET /version")
        handle_version
        ;;
    "POST /update")
        # Drain body (we don't use it but must consume Content-Length bytes
        # so socat doesn't keep the socket half-open).
        if [ "${REQ_CONTENT_LENGTH:-0}" -gt 0 ] 2>/dev/null; then
            dd bs=1 count="$REQ_CONTENT_LENGTH" of=/dev/null 2>/dev/null || true
        fi
        # Auth: expect "Authorization: Bearer <token>".
        case "$REQ_AUTH" in
            Bearer\ *)
                token="${REQ_AUTH#Bearer }"
                if check_token "$token"; then
                    handle_update
                else
                    log "auth failed (bad token)"
                    respond 401 Unauthorized '{"error":"invalid_token"}'
                fi
                ;;
            *)
                log "auth failed (no bearer)"
                respond 401 Unauthorized '{"error":"missing_authorization"}'
                ;;
        esac
        ;;
    *)
        respond 404 "Not Found" '{"error":"not_found"}'
        ;;
esac
