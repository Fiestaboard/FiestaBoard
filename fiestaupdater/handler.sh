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
#   POST /rollback        → 202  {"status":"queued"}    (requires Bearer auth)
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
#   - /rollback's body is JSON containing a target digest and image
#     reference; both are validated against strict regexes before being
#     passed to `docker tag` / `docker compose`.
#   - The listener is *not* published to the host (compose-network only).
#
# /update behaviour:
#   * ``docker compose pull`` + ``up -d --no-deps`` for the service.  We do
#     **not** automatically roll back on health-probe failure: the user
#     decides if and when to roll back via /rollback.  We do, however,
#     snapshot the pre-update digest + image reference into
#     ``${FIESTAUPDATER_STATE_DIR}/last-update.json`` so the main API and
#     UI can offer a one-click "go back to the previous version" affordance.
#
# /rollback behaviour:
#   * Body: ``{"digest":"sha256:<hex>","image":"repo[:tag]"}``.
#   * Retag the supplied digest onto the supplied image reference and
#     ``docker compose up -d --no-deps --force-recreate`` so the running
#     container is replaced with the rollback target.
# =============================================================================
set -u

PORT="${FIESTAUPDATER_PORT:-8765}"
COMPOSE_FILE="${FIESTAUPDATER_COMPOSE_FILE:-/compose/docker-compose.yml}"
SERVICE="${FIESTAUPDATER_SERVICE:-fiestaboard}"

# Where we persist the result of the most recent /update or /rollback
# attempt.  This file is read by GET /last-update (no auth) so the main
# fiestaboard UI can show what version we are now on without needing
# another channel.
STATE_DIR="${FIESTAUPDATER_STATE_DIR:-/var/lib/fiestaupdater}"
STATE_FILE="${STATE_DIR}/last-update.json"

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
# Persist the result of the most recent update / rollback attempt so the
# main fiestaboard API can surface it in /system/update/status.  Writes
# are best-effort: a missing/unwritable STATE_DIR is logged and ignored
# rather than aborting the operation.
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
# GET /last-update — return the persisted result of the most recent
# /update or /rollback attempt.  No auth required: this is read-only
# status.  If no attempt has been made yet (or the state file was lost),
# return a benign placeholder.
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
#
# We snapshot the pre-update digest + image reference into the state
# file so the main API can offer a one-click rollback to that exact
# version later.  We do **not** automatically roll back on probe
# failure — the user decides whether/when to roll back.
# ---------------------------------------------------------------------------
handle_update() {
    log "update requested for service=${SERVICE}"
    if [ ! -f "$COMPOSE_FILE" ]; then
        log "compose file missing at ${COMPOSE_FILE}"
        respond 500 "Internal Server Error" '{"error":"compose_file_missing"}'
        return
    fi
    # Capture the digest *and* image reference before we pull.  The image
    # reference (e.g. ``fiestaboard/fiestaboard:latest``) is what /rollback
    # will retag the saved digest onto, so capturing it now — before the
    # new image overwrites the tag — is mandatory.
    local before before_image
    before=$(docker inspect --format '{{.Image}}' "$SERVICE" 2>/dev/null || echo "")
    before_image=$(docker inspect --format '{{.Config.Image}}' "$SERVICE" 2>/dev/null || echo "")
    log "pre-update digest=${before} image=${before_image}"

    # Mark the attempt as in-progress immediately so the main API can
    # display "updating…" while the recreate runs.
    local started_at
    started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    write_state "{\"status\":\"in_progress\",\"action\":\"update\",\"service\":\"${SERVICE}\",\"previous_digest\":\"${before}\",\"previous_image\":\"${before_image}\",\"started_at\":\"${started_at}\"}"

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

    nohup bash -c '
        set -u
        _write_state() {
            mkdir -p "$FU_STATE_DIR" 2>/dev/null || true
            local tmp="${FU_STATE_FILE}.tmp"
            printf "%s" "$1" >"$tmp" 2>/dev/null && mv -f "$tmp" "$FU_STATE_FILE" 2>/dev/null
        }

        echo "[fiestaupdater] pulling latest image for ${FU_SERVICE}..."
        if ! docker compose -f "$FU_COMPOSE_FILE" pull "$FU_SERVICE"; then
            completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
            _write_state "{\"status\":\"failed\",\"action\":\"update\",\"service\":\"${FU_SERVICE}\",\"previous_digest\":\"${FU_BEFORE_DIGEST}\",\"previous_image\":\"${FU_BEFORE_IMAGE}\",\"error\":\"pull_failed\",\"completed_at\":\"${completed_at}\"}"
            echo "[fiestaupdater] pull failed; aborting without recreate"
            exit 0
        fi

        echo "[fiestaupdater] recreating ${FU_SERVICE}..."
        docker compose -f "$FU_COMPOSE_FILE" up -d --no-deps "$FU_SERVICE"
        after=$(docker inspect --format "{{.Image}}" "$FU_SERVICE" 2>/dev/null || echo "")
        completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
        echo "[fiestaupdater] update succeeded; new digest=${after}"
        _write_state "{\"status\":\"success\",\"action\":\"update\",\"service\":\"${FU_SERVICE}\",\"previous_digest\":\"${FU_BEFORE_DIGEST}\",\"previous_image\":\"${FU_BEFORE_IMAGE}\",\"new_digest\":\"${after}\",\"completed_at\":\"${completed_at}\"}"
    ' >>"$logsink" 2>&1 &

    respond 202 Accepted "{\"status\":\"queued\",\"action\":\"update\",\"service\":\"${SERVICE}\",\"previous_digest\":\"${before}\",\"previous_image\":\"${before_image}\"}"
}

# ---------------------------------------------------------------------------
# POST /rollback — user-initiated rollback to a specific image digest.
#
# Body (JSON, required):
#   { "digest": "sha256:<64 hex>", "image": "repo[:tag]" }
#
# We retag the supplied digest back onto the supplied image reference and
# force-recreate the service so it picks the rollback target up.  The
# digest must already exist locally — typically because the user is
# rolling back to the version they were on before the last /update.
#
# Both fields are validated with strict regexes; if either fails to
# match we respond 400 and never invoke ``docker``.
# ---------------------------------------------------------------------------
handle_rollback() {
    log "rollback requested for service=${SERVICE}"
    if [ ! -f "$COMPOSE_FILE" ]; then
        log "compose file missing at ${COMPOSE_FILE}"
        respond 500 "Internal Server Error" '{"error":"compose_file_missing"}'
        return
    fi

    local body="${REQ_BODY:-}"
    # Extract digest + image from the JSON body.  We do not bring in jq
    # to keep the alpine image small; a small grep is sufficient because
    # we then validate every captured value against a strict regex below.
    # The regex *is* the security boundary here — even if the extraction
    # mis-parses a body containing backslash-escaped quotes, the strict
    # `^sha256:[a-f0-9]{64}$` and image-reference allow-list will reject
    # anything that isn't an exact match before either value is passed
    # to ``docker``.  The body is also size-capped to 8 KiB upstream.
    local digest image
    digest=$(printf '%s' "$body" | grep -oE '"digest"[[:space:]]*:[[:space:]]*"[^"]*"' | head -n1 | sed -E 's/.*"digest"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/')
    image=$(printf '%s' "$body" | grep -oE '"image"[[:space:]]*:[[:space:]]*"[^"]*"' | head -n1 | sed -E 's/.*"image"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/')

    # Validate.  Digest must be ``sha256:<64 hex>``; image must be a
    # plausible Docker image reference: lowercase alphanumerics, dots,
    # underscores, hyphens, slashes, and an optional :tag suffix.
    if ! [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]; then
        log "rollback: invalid digest"
        respond 400 "Bad Request" '{"error":"invalid_digest"}'
        return
    fi
    if ! [[ "$image" =~ ^[a-z0-9][a-z0-9._/-]{0,199}(:[a-zA-Z0-9._-]{1,128})?$ ]]; then
        log "rollback: invalid image reference"
        respond 400 "Bad Request" '{"error":"invalid_image"}'
        return
    fi

    local started_at
    started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local current_digest
    current_digest=$(docker inspect --format '{{.Image}}' "$SERVICE" 2>/dev/null || echo "")
    write_state "{\"status\":\"in_progress\",\"action\":\"rollback\",\"service\":\"${SERVICE}\",\"target_digest\":\"${digest}\",\"target_image\":\"${image}\",\"previous_digest\":\"${current_digest}\",\"started_at\":\"${started_at}\"}"

    local logsink
    if [ -e /proc/1/fd/2 ]; then
        logsink=/proc/1/fd/2
    else
        logsink=/dev/null
    fi
    export FU_SERVICE="$SERVICE"
    export FU_COMPOSE_FILE="$COMPOSE_FILE"
    export FU_TARGET_DIGEST="$digest"
    export FU_TARGET_IMAGE="$image"
    export FU_PREVIOUS_DIGEST="$current_digest"
    export FU_STATE_FILE="$STATE_FILE"
    export FU_STATE_DIR="$STATE_DIR"

    nohup bash -c '
        set -u
        _write_state() {
            mkdir -p "$FU_STATE_DIR" 2>/dev/null || true
            local tmp="${FU_STATE_FILE}.tmp"
            printf "%s" "$1" >"$tmp" 2>/dev/null && mv -f "$tmp" "$FU_STATE_FILE" 2>/dev/null
        }

        echo "[fiestaupdater] rolling back ${FU_SERVICE} to ${FU_TARGET_DIGEST} (image=${FU_TARGET_IMAGE})"
        if ! docker tag "$FU_TARGET_DIGEST" "$FU_TARGET_IMAGE"; then
            completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
            echo "[fiestaupdater] docker tag failed during rollback (target image not present locally?)"
            _write_state "{\"status\":\"rollback_failed\",\"action\":\"rollback\",\"service\":\"${FU_SERVICE}\",\"target_digest\":\"${FU_TARGET_DIGEST}\",\"target_image\":\"${FU_TARGET_IMAGE}\",\"previous_digest\":\"${FU_PREVIOUS_DIGEST}\",\"error\":\"retag_failed\",\"completed_at\":\"${completed_at}\"}"
            exit 0
        fi
        docker compose -f "$FU_COMPOSE_FILE" up -d --no-deps --force-recreate "$FU_SERVICE"
        rolled_to=$(docker inspect --format "{{.Image}}" "$FU_SERVICE" 2>/dev/null || echo "")
        completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
        echo "[fiestaupdater] rollback complete; service now on ${rolled_to}"
        _write_state "{\"status\":\"rolled_back\",\"action\":\"rollback\",\"service\":\"${FU_SERVICE}\",\"target_digest\":\"${FU_TARGET_DIGEST}\",\"target_image\":\"${FU_TARGET_IMAGE}\",\"previous_digest\":\"${FU_PREVIOUS_DIGEST}\",\"rolled_back_to\":\"${rolled_to}\",\"completed_at\":\"${completed_at}\"}"
    ' >>"$logsink" 2>&1 &

    respond 202 Accepted "{\"status\":\"queued\",\"action\":\"rollback\",\"service\":\"${SERVICE}\",\"target_digest\":\"${digest}\",\"target_image\":\"${image}\"}"
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
    "POST /update"|"POST /rollback"|"POST /restart"|"POST /shutdown")
        # For routes that take a body (currently just /rollback), capture
        # it; for the others, drain Content-Length bytes so socat doesn't
        # keep the socket half-open.
        REQ_BODY=""
        if [ "${REQ_CONTENT_LENGTH:-0}" -gt 0 ] 2>/dev/null; then
            if [ "${REQ_METHOD} ${REQ_PATH}" = "POST /rollback" ]; then
                # Cap body size at 8 KiB — /rollback's payload is two
                # short strings; anything larger is malformed or hostile.
                _read="$REQ_CONTENT_LENGTH"
                if [ "$_read" -gt 8192 ]; then _read=8192; fi
                REQ_BODY="$(dd bs=1 count="$_read" 2>/dev/null || true)"
            else
                dd bs=1 count="$REQ_CONTENT_LENGTH" of=/dev/null 2>/dev/null || true
            fi
        fi
        # Auth: expect "Authorization: Bearer <token>".
        case "$REQ_AUTH" in
            Bearer\ *)
                token="${REQ_AUTH#Bearer }"
                if check_token "$token"; then
                    case "${REQ_METHOD} ${REQ_PATH}" in
                        "POST /update")   handle_update ;;
                        "POST /rollback") handle_rollback ;;
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
