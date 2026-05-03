#!/bin/bash
# =============================================================================
# FiestaUpdater per-connection HTTP handler.
# Invoked by socat with stdin/stdout bound to the client socket.
#
# Routes:
#   GET  /healthz         → 200  {"status":"ok"}
#   GET  /version         → 200  {"image":"<repo:tag>","digest":"<sha256:...>"}
#   GET  /last-update     → 200  {"status":"...", ...}  (last update result)
#   POST /update          → 202  {"status":"queued"}    (requires Bearer auth)
#   POST /restart         → 202                         (requires Bearer auth)
#   POST /shutdown        → 202                         (requires Bearer auth)
#
# Security notes:
#   - Authentication: shared bearer token from FIESTAUPDATER_TOKEN env.
#     Compared via SHA-256 hash to reduce timing-attack surface.
#   - The compose service name is read from env but additionally validated
#     against a strict allow-list pattern ([a-z0-9_-]+) before being passed
#     to `docker compose`.  No user input is ever interpolated into a shell
#     command.
#   - The listener is *not* published to the host (compose-network only).
#
# Rollback behaviour for /update:
#   1. Snapshot the running container's image digest *and* image reference
#      (e.g. ``fiestaboard/fiestaboard:latest``) before pulling.
#   2. ``docker compose pull`` + ``up -d --no-deps`` for the service.
#   3. Probe ``${FIESTAUPDATER_PROBE_URL}`` (default
#      ``http://${SERVICE}:3000/api/health``) for up to
#      ``${FIESTAUPDATER_PROBE_TIMEOUT_SECS}`` seconds (default 60).
#   4. If the probe never returns HTTP 200, retag the saved digest back onto
#      the original image reference and ``up -d --force-recreate`` again so
#      the user is left on a known-good version.
#   5. Either way, write a JSON status document to
#      ``${FIESTAUPDATER_STATE_DIR}/last-update.json`` for the main API to
#      surface in ``GET /system/update/status`` (and the new
#      ``GET /last-update`` route on this sidecar).
# =============================================================================
set -u

PORT="${FIESTAUPDATER_PORT:-8765}"
COMPOSE_FILE="${FIESTAUPDATER_COMPOSE_FILE:-/compose/docker-compose.yml}"
SERVICE="${FIESTAUPDATER_SERVICE:-fiestaboard}"

# Where we persist the result of the most recent /update attempt.  This file
# is read by GET /last-update (no auth) so the main fiestaboard UI can show
# "Update failed; reverted to <digest>" without needing another channel.
STATE_DIR="${FIESTAUPDATER_STATE_DIR:-/var/lib/fiestaupdater}"
STATE_FILE="${STATE_DIR}/last-update.json"

# Health probe knobs.  Overridable from the environment so tests (and
# advanced operators) can point the probe at a stub server / loopback URL.
PROBE_URL="${FIESTAUPDATER_PROBE_URL:-http://${SERVICE}:3000/api/health}"
PROBE_TIMEOUT_SECS="${FIESTAUPDATER_PROBE_TIMEOUT_SECS:-60}"
PROBE_INTERVAL_SECS="${FIESTAUPDATER_PROBE_INTERVAL_SECS:-2}"

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
# Persist the result of the most recent update attempt so the main
# fiestaboard API can surface it in /system/update/status.  Writes are
# best-effort: a missing/unwritable STATE_DIR is logged and ignored
# rather than aborting the update.
# ---------------------------------------------------------------------------
write_state() {
    local body="$1"
    mkdir -p "$STATE_DIR" 2>/dev/null || {
        log "could not create state dir ${STATE_DIR}"
        return 0
    }
    local tmp="${STATE_FILE}.tmp"
    if ! printf '%s' "$body" >"$tmp" 2>/dev/null; then
        log "could not write state file ${tmp}"
        return 0
    fi
    mv -f "$tmp" "$STATE_FILE" 2>/dev/null || log "could not move state file into place"
}

# ---------------------------------------------------------------------------
# Single attempt at the FiestaBoard health probe.  Returns 0 iff the
# configured ${PROBE_URL} responded with HTTP 200 within the per-attempt
# timeout.  Uses busybox `wget` (already on docker:cli's alpine base).
# ---------------------------------------------------------------------------
probe_once() {
    wget -q -O /dev/null --tries=1 --timeout=5 "$PROBE_URL"
}

# ---------------------------------------------------------------------------
# Poll ${PROBE_URL} every PROBE_INTERVAL_SECS for up to PROBE_TIMEOUT_SECS.
# Returns 0 if any poll succeeds, 1 otherwise.  We do not log on every
# failed attempt — that would be very noisy during a normal restart.
# ---------------------------------------------------------------------------
probe_until_healthy() {
    local deadline=$(( $(date +%s) + PROBE_TIMEOUT_SECS ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if probe_once; then
            return 0
        fi
        sleep "$PROBE_INTERVAL_SECS"
    done
    return 1
}

# ---------------------------------------------------------------------------
# GET /last-update — return the persisted result of the most recent /update
# attempt.  No auth required: this is read-only status.  If no attempt has
# been made yet (or the state file was lost), return a benign placeholder.
# ---------------------------------------------------------------------------
handle_last_update() {
    if [ -f "$STATE_FILE" ]; then
        local body
        body=$(cat "$STATE_FILE" 2>/dev/null || echo '')
        if [ -n "$body" ]; then
            respond 200 OK "$body"
            return
        fi
    fi
    respond 200 OK '{"status":"none"}'
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
# POST /restart — restart the service container in-place.
# Returns 202 immediately; docker compose restart is run in the background
# because it will kill the fiestaboard container (and this HTTP connection)
# before the response would otherwise be flushed.
# ---------------------------------------------------------------------------
handle_restart() {
    log "restart requested for service=${SERVICE}"
    if [ ! -f "$COMPOSE_FILE" ]; then
        log "compose file missing at ${COMPOSE_FILE}"
        respond 500 "Internal Server Error" '{"error":"compose_file_missing"}'
        return
    fi
    local logsink
    if [ -e /proc/1/fd/2 ]; then
        logsink=/proc/1/fd/2
    else
        logsink=/dev/null
    fi
    nohup bash -c "
        set -eu
        echo '[fiestaupdater] restarting ${SERVICE}...'
        docker compose -f '${COMPOSE_FILE}' restart '${SERVICE}'
        echo '[fiestaupdater] restart complete'
    " >>"$logsink" 2>&1 &
    respond 202 Accepted "{\"status\":\"queued\",\"action\":\"restart\",\"service\":\"${SERVICE}\"}"
}

# ---------------------------------------------------------------------------
# POST /shutdown — gracefully power off the host machine.
# Stops the compose service first, then calls poweroff.
# Requires the container to have the SYS_BOOT capability
# (cap_add: [SYS_BOOT] in docker-compose.yml).
# ---------------------------------------------------------------------------
handle_shutdown() {
    log "host shutdown requested"
    local logsink
    if [ -e /proc/1/fd/2 ]; then
        logsink=/proc/1/fd/2
    else
        logsink=/dev/null
    fi
    nohup bash -c "
        echo '[fiestaupdater] stopping services before shutdown...'
        docker compose -f '${COMPOSE_FILE}' stop || true
        echo '[fiestaupdater] initiating host poweroff...'
        poweroff -f
    " >>"$logsink" 2>&1 &
    respond 202 Accepted '{"status":"queued","action":"shutdown"}'
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
    # Capture the digest *and* image reference before we pull.  The image
    # reference (e.g. ``fiestaboard/fiestaboard:latest``) is what we will
    # retag the saved digest onto if we have to roll back, so capturing it
    # now — before the new image overwrites the tag — is mandatory.
    local before before_image
    before=$(docker inspect --format '{{.Image}}' "$SERVICE" 2>/dev/null || echo "")
    before_image=$(docker inspect --format '{{.Config.Image}}' "$SERVICE" 2>/dev/null || echo "")
    log "pre-update digest=${before} image=${before_image}"

    # Mark the attempt as in-progress immediately so the main API can
    # display "updating…" while the recreate runs.
    local started_at
    started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    write_state "{\"status\":\"in_progress\",\"service\":\"${SERVICE}\",\"previous_digest\":\"${before}\",\"previous_image\":\"${before_image}\",\"started_at\":\"${started_at}\"}"

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
    # Export everything the background script needs.  We deliberately pass
    # values through the environment rather than interpolating them into the
    # bash -c argument: it keeps the script free of injection seams.
    export FU_SERVICE="$SERVICE"
    export FU_COMPOSE_FILE="$COMPOSE_FILE"
    export FU_BEFORE_DIGEST="$before"
    export FU_BEFORE_IMAGE="$before_image"
    export FU_STATE_FILE="$STATE_FILE"
    export FU_STATE_DIR="$STATE_DIR"
    export FU_PROBE_URL="$PROBE_URL"
    export FU_PROBE_TIMEOUT_SECS="$PROBE_TIMEOUT_SECS"
    export FU_PROBE_INTERVAL_SECS="$PROBE_INTERVAL_SECS"

    nohup bash -c '
        set -u
        # Helpers (duplicated from the parent because the background shell is
        # a fresh process; keeping them inline avoids sourcing handler.sh
        # recursively).
        _write_state() {
            mkdir -p "$FU_STATE_DIR" 2>/dev/null || true
            local tmp="${FU_STATE_FILE}.tmp"
            printf "%s" "$1" >"$tmp" 2>/dev/null && mv -f "$tmp" "$FU_STATE_FILE" 2>/dev/null
        }
        _probe_once() {
            wget -q -O /dev/null --tries=1 --timeout=5 "$FU_PROBE_URL"
        }
        _probe_until_healthy() {
            local deadline=$(( $(date +%s) + FU_PROBE_TIMEOUT_SECS ))
            while [ "$(date +%s)" -lt "$deadline" ]; do
                if _probe_once; then return 0; fi
                sleep "$FU_PROBE_INTERVAL_SECS"
            done
            return 1
        }

        echo "[fiestaupdater] pulling latest image for ${FU_SERVICE}..."
        if ! docker compose -f "$FU_COMPOSE_FILE" pull "$FU_SERVICE"; then
            completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
            _write_state "{\"status\":\"failed\",\"service\":\"${FU_SERVICE}\",\"previous_digest\":\"${FU_BEFORE_DIGEST}\",\"previous_image\":\"${FU_BEFORE_IMAGE}\",\"error\":\"pull_failed\",\"completed_at\":\"${completed_at}\"}"
            echo "[fiestaupdater] pull failed; aborting without recreate"
            exit 0
        fi

        echo "[fiestaupdater] recreating ${FU_SERVICE}..."
        docker compose -f "$FU_COMPOSE_FILE" up -d --no-deps "$FU_SERVICE"
        after=$(docker inspect --format "{{.Image}}" "$FU_SERVICE" 2>/dev/null || echo "")
        echo "[fiestaupdater] post-update digest=${after}"

        echo "[fiestaupdater] probing ${FU_PROBE_URL} for up to ${FU_PROBE_TIMEOUT_SECS}s..."
        if _probe_until_healthy; then
            completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
            echo "[fiestaupdater] update succeeded; new digest=${after}"
            _write_state "{\"status\":\"success\",\"service\":\"${FU_SERVICE}\",\"previous_digest\":\"${FU_BEFORE_DIGEST}\",\"previous_image\":\"${FU_BEFORE_IMAGE}\",\"new_digest\":\"${after}\",\"completed_at\":\"${completed_at}\"}"
            exit 0
        fi

        echo "[fiestaupdater] health probe failed after ${FU_PROBE_TIMEOUT_SECS}s; rolling back to ${FU_BEFORE_DIGEST}"
        # Mark "in_progress" → "rolling_back" so a UI polling /last-update
        # sees the intent before the rollback finishes.
        _write_state "{\"status\":\"rolling_back\",\"service\":\"${FU_SERVICE}\",\"previous_digest\":\"${FU_BEFORE_DIGEST}\",\"previous_image\":\"${FU_BEFORE_IMAGE}\",\"failed_digest\":\"${after}\"}"

        if [ -z "$FU_BEFORE_DIGEST" ] || [ -z "$FU_BEFORE_IMAGE" ]; then
            completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
            echo "[fiestaupdater] cannot roll back: pre-update digest or image was unknown"
            _write_state "{\"status\":\"rollback_unavailable\",\"service\":\"${FU_SERVICE}\",\"previous_digest\":\"${FU_BEFORE_DIGEST}\",\"previous_image\":\"${FU_BEFORE_IMAGE}\",\"failed_digest\":\"${after}\",\"error\":\"missing_pre_update_state\",\"completed_at\":\"${completed_at}\"}"
            exit 0
        fi

        # Pin the previous digest back onto the image reference compose
        # uses, then force-recreate so the new container picks it up.
        if ! docker tag "$FU_BEFORE_DIGEST" "$FU_BEFORE_IMAGE"; then
            completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
            echo "[fiestaupdater] docker tag failed during rollback"
            _write_state "{\"status\":\"rollback_failed\",\"service\":\"${FU_SERVICE}\",\"previous_digest\":\"${FU_BEFORE_DIGEST}\",\"previous_image\":\"${FU_BEFORE_IMAGE}\",\"failed_digest\":\"${after}\",\"error\":\"retag_failed\",\"completed_at\":\"${completed_at}\"}"
            exit 0
        fi
        docker compose -f "$FU_COMPOSE_FILE" up -d --no-deps --force-recreate "$FU_SERVICE"
        rolled_to=$(docker inspect --format "{{.Image}}" "$FU_SERVICE" 2>/dev/null || echo "")
        completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
        # Probe once more so we can tell the user whether the rollback
        # itself recovered the service.  We use a short window (the
        # rollback target is a known-good image, so it should answer
        # quickly).
        if _probe_until_healthy; then
            echo "[fiestaupdater] rollback complete; service healthy on ${rolled_to}"
            _write_state "{\"status\":\"rolled_back\",\"service\":\"${FU_SERVICE}\",\"previous_digest\":\"${FU_BEFORE_DIGEST}\",\"previous_image\":\"${FU_BEFORE_IMAGE}\",\"failed_digest\":\"${after}\",\"rolled_back_to\":\"${rolled_to}\",\"completed_at\":\"${completed_at}\"}"
        else
            echo "[fiestaupdater] rollback complete but service is still unhealthy on ${rolled_to}"
            _write_state "{\"status\":\"rolled_back_unhealthy\",\"service\":\"${FU_SERVICE}\",\"previous_digest\":\"${FU_BEFORE_DIGEST}\",\"previous_image\":\"${FU_BEFORE_IMAGE}\",\"failed_digest\":\"${after}\",\"rolled_back_to\":\"${rolled_to}\",\"completed_at\":\"${completed_at}\"}"
        fi
    ' >>"$logsink" 2>&1 &

    respond 202 Accepted "{\"status\":\"queued\",\"service\":\"${SERVICE}\",\"previous_digest\":\"${before}\",\"previous_image\":\"${before_image}\"}"
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
    "GET /last-update")
        handle_last_update
        ;;
    "POST /update"|"POST /restart"|"POST /shutdown")
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
                    case "${REQ_METHOD} ${REQ_PATH}" in
                        "POST /update")   handle_update ;;
                        "POST /restart")  handle_restart ;;
                        "POST /shutdown") handle_shutdown ;;
                    esac
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
