#!/usr/bin/env bats
# =============================================================================
# Tests for fiestaupdater/handler.sh
#
# Strategy: run handler.sh as a subprocess, feed it raw HTTP on stdin,
# capture the raw HTTP response on stdout.  A fake `docker` binary on PATH
# stands in for the real Docker CLI so we never touch the host.
# =============================================================================

setup() {
    HANDLER="${BATS_TEST_DIRNAME}/../handler.sh"
    [ -x "$HANDLER" ] || chmod +x "$HANDLER"

    # Sandbox: a temp dir that holds a fake `docker`, a compose file, and
    # somewhere to record the calls the handler makes.
    SANDBOX="$(mktemp -d)"
    export PATH="${SANDBOX}:${PATH}"
    export FIESTAUPDATER_TOKEN="test-token-abc"
    export FIESTAUPDATER_PORT=18765
    export FIESTAUPDATER_SERVICE="fiestaboard"
    export FIESTAUPDATER_COMPOSE_FILE="${SANDBOX}/docker-compose.yml"
    # State (last-update.json) lives in the sandbox so each test starts
    # from a clean slate.
    export FIESTAUPDATER_STATE_DIR="${SANDBOX}/state"

    cat >"${SANDBOX}/docker-compose.yml" <<'YAML'
services:
  fiestaboard:
    image: fiestaboard/fiestaboard:latest
YAML

    # Fake docker that records its argv and returns canned values.
    cat >"${SANDBOX}/docker" <<'SH'
#!/bin/sh
echo "$@" >> "${SANDBOX}/docker.calls"
case "$1" in
    inspect)
        # `docker inspect --format '{{.Config.Image}}' fiestaboard` etc.
        case "$3" in
            *Config.Image*) echo "fiestaboard/fiestaboard:latest" ;;
            *Image*)        echo "sha256:abc123" ;;
            *)              echo "" ;;
        esac
        ;;
    compose|tag)
        # Always succeed.
        exit 0
        ;;
    *)
        exit 0
        ;;
esac
SH
    chmod +x "${SANDBOX}/docker"
    export SANDBOX
}

teardown() {
    rm -rf "$SANDBOX"
}

# ---- helpers ---------------------------------------------------------------

# Send a raw HTTP request to the handler and capture the response.
send() {
    printf '%s' "$1" | bash "$HANDLER"
}

# Extract the HTTP status line.
status_of() {
    printf '%s' "$1" | head -n1 | tr -d '\r'
}

# ---- /healthz --------------------------------------------------------------

@test "GET /healthz returns 200" {
    req=$'GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 200 OK" ]]
    [[ "$out" == *'"status":"ok"'* ]]
}

# ---- /version --------------------------------------------------------------

@test "GET /version returns image and digest" {
    req=$'GET /version HTTP/1.1\r\nHost: x\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 200 OK" ]]
    [[ "$out" == *'"image":"fiestaboard/fiestaboard:latest"'* ]]
    [[ "$out" == *'"digest":"sha256:abc123"'* ]]
}

# ---- /update : auth --------------------------------------------------------

@test "POST /update with no Authorization → 401" {
    req=$'POST /update HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 401 Unauthorized" ]]
    [[ "$out" == *missing_authorization* ]]
}

@test "POST /update with wrong bearer token → 401" {
    req=$'POST /update HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer wrong\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 401 Unauthorized" ]]
    [[ "$out" == *invalid_token* ]]
}

@test "POST /update with non-Bearer scheme → 401" {
    req=$'POST /update HTTP/1.1\r\nHost: x\r\nAuthorization: Basic abc\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 401 Unauthorized" ]]
}

# ---- /update : happy path --------------------------------------------------

@test "POST /update with valid token → 202 and triggers compose" {
    req=$'POST /update HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 202 Accepted" ]]
    [[ "$out" == *'"status":"queued"'* ]]
    # The compose run is launched in the background by the handler.  Give it
    # a moment to invoke our fake docker and record the call.
    sleep 1
    grep -q "compose -f" "${SANDBOX}/docker.calls"
    grep -q "pull fiestaboard" "${SANDBOX}/docker.calls"
    grep -q "up -d --no-deps fiestaboard" "${SANDBOX}/docker.calls"
}

# ---- service-name allow-list ----------------------------------------------

@test "shell-metachar service name is rejected and falls back to fiestaboard" {
    export FIESTAUPDATER_SERVICE='fiestaboard;rm -rf /'
    req=$'POST /update HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 202 Accepted" ]]
    sleep 1
    # The fake docker recorded the actual service name passed.
    # It must be the safe fallback, never the malicious value.
    grep -q "pull fiestaboard$" "${SANDBOX}/docker.calls"
    ! grep -q "rm -rf" "${SANDBOX}/docker.calls"
}

# ---- FIESTAUPDATER_PROJECT_DIR --------------------------------------------
# Regression test for the Docker Hub install bug where relative bind mounts
# in the compose file (e.g. `./data:/app/data`) were being resolved against
# `/compose/` inside the sidecar instead of the host project directory.
# When FIESTAUPDATER_PROJECT_DIR is set, every compose invocation must
# forward it as `--project-directory <dir>` so Compose sees the right path.

@test "POST /update forwards FIESTAUPDATER_PROJECT_DIR as --project-directory" {
    export FIESTAUPDATER_PROJECT_DIR="/host/project"
    req=$'POST /update HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 202 Accepted" ]]
    sleep 1
    # Both the pull and the up calls must carry --project-directory.
    grep -qE 'compose --project-directory /host/project -f .* pull fiestaboard' "${SANDBOX}/docker.calls"
    grep -qE 'compose --project-directory /host/project -f .* up -d --no-deps fiestaboard' "${SANDBOX}/docker.calls"
}

@test "POST /restart forwards FIESTAUPDATER_PROJECT_DIR as --project-directory" {
    export FIESTAUPDATER_PROJECT_DIR="/host/project"
    req=$'POST /restart HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 202 Accepted" ]]
    sleep 1
    grep -qE 'compose --project-directory /host/project -f .* restart fiestaboard' "${SANDBOX}/docker.calls"
}

@test "non-absolute FIESTAUPDATER_PROJECT_DIR is ignored" {
    # A relative value would be resolved against the sidecar's cwd (/), which
    # is never what the user wants.  Reject it and run compose without
    # --project-directory rather than silently producing /<rel> on the host.
    export FIESTAUPDATER_PROJECT_DIR="relative/path"
    req=$'POST /update HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 202 Accepted" ]]
    sleep 1
    # The fake docker was still invoked, but without --project-directory.
    grep -q "pull fiestaboard" "${SANDBOX}/docker.calls"
    ! grep -q "project-directory" "${SANDBOX}/docker.calls"
}

# ---- /update : failure surfacing ------------------------------------------
# Regression test for the "update succeeded" misreporting bug: when
# `docker compose up -d` fails (e.g. because a bind-mount source doesn't
# exist on the host), the updater must persist a `failed` state instead
# of writing `success`, so the UI can show the user that things are broken.

@test "POST /update writes status=failed when compose up exits non-zero" {
    # Replace the fake docker with one that succeeds for pull but fails for `up`.
    cat >"${SANDBOX}/docker" <<'SH'
#!/bin/sh
echo "$@" >> "${SANDBOX}/docker.calls"
case "$1" in
    inspect)
        case "$3" in
            *Config.Image*) echo "fiestaboard/fiestaboard:latest" ;;
            *Image*)        echo "sha256:abc123" ;;
            *)              echo "" ;;
        esac
        ;;
    compose)
        # Walk argv looking for the verb after the flags.
        shift
        while [ $# -gt 0 ]; do
            case "$1" in
                --project-directory|-f) shift 2;;
                pull) exit 0;;
                up)   exit 1;;
                *)    shift;;
            esac
        done
        exit 0
        ;;
    *) exit 0 ;;
esac
SH
    chmod +x "${SANDBOX}/docker"

    req=$'POST /update HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    send "$req" >/dev/null
    # Wait for the background worker to finish writing state.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        if [ -f "${SANDBOX}/state/last-update.json" ] && \
           grep -q '"status":"failed"' "${SANDBOX}/state/last-update.json"; then
            break
        fi
        sleep 1
    done

    [ -f "${SANDBOX}/state/last-update.json" ]
    grep -q '"status":"failed"' "${SANDBOX}/state/last-update.json"
    grep -q '"error":"recreate_failed"' "${SANDBOX}/state/last-update.json"
    ! grep -q '"status":"success"' "${SANDBOX}/state/last-update.json"
}

# ---- unknown route ---------------------------------------------------------

@test "GET /nonsense → 404" {
    req=$'GET /nonsense HTTP/1.1\r\nHost: x\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 404 Not Found" ]]
}

# ---- /restart --------------------------------------------------------------

@test "POST /restart with no Authorization → 401" {
    req=$'POST /restart HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 401 Unauthorized" ]]
    [[ "$out" == *missing_authorization* ]]
}

@test "POST /restart with wrong token → 401" {
    req=$'POST /restart HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer wrong\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 401 Unauthorized" ]]
    [[ "$out" == *invalid_token* ]]
}

@test "POST /restart with valid token → 202 and triggers compose restart" {
    req=$'POST /restart HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 202 Accepted" ]]
    [[ "$out" == *'"status":"queued"'* ]]
    [[ "$out" == *'"action":"restart"'* ]]
    sleep 1
    grep -q "compose -f" "${SANDBOX}/docker.calls"
    grep -q "restart fiestaboard" "${SANDBOX}/docker.calls"
}

# ---- /shutdown -------------------------------------------------------------

@test "POST /shutdown with no Authorization → 401" {
    req=$'POST /shutdown HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 401 Unauthorized" ]]
    [[ "$out" == *missing_authorization* ]]
}

@test "POST /shutdown with wrong token → 401" {
    req=$'POST /shutdown HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer wrong\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 401 Unauthorized" ]]
    [[ "$out" == *invalid_token* ]]
}

@test "POST /shutdown with valid token → 202" {
    # Override poweroff with a no-op so the test host doesn't actually shut down.
    cat >"${SANDBOX}/poweroff" <<'SH'
#!/bin/sh
echo "poweroff $@" >> "${SANDBOX}/poweroff.calls"
SH
    chmod +x "${SANDBOX}/poweroff"

    req=$'POST /shutdown HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 202 Accepted" ]]
    [[ "$out" == *'"status":"queued"'* ]]
    [[ "$out" == *'"action":"shutdown"'* ]]
}

# ---- malformed -------------------------------------------------------------

@test "empty input → 400" {
    out=$(send "")
    [[ "$(status_of "$out")" == "HTTP/1.1 400 Bad Request" ]]
}

# ---- /last-update ---------------------------------------------------------

@test "GET /last-update with no prior attempt returns placeholder" {
    req=$'GET /last-update HTTP/1.1\r\nHost: x\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 200 OK" ]]
    [[ "$out" == *'"status":"none"'* ]]
}

@test "GET /last-update reflects success after a healthy update" {
    req=$'POST /update HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    send "$req" >/dev/null
    # Wait for the background worker to finish writing state.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        if [ -f "${SANDBOX}/state/last-update.json" ] && \
           grep -q '"status":"success"' "${SANDBOX}/state/last-update.json"; then
            break
        fi
        sleep 1
    done

    req=$'GET /last-update HTTP/1.1\r\nHost: x\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 200 OK" ]]
    [[ "$out" == *'"status":"success"'* ]]
    [[ "$out" == *'"previous_digest":"sha256:abc123"'* ]]
    [[ "$out" == *'"previous_image":"fiestaboard/fiestaboard:latest"'* ]]
}

# ---- /rollback ------------------------------------------------------------

@test "POST /rollback with no Authorization → 401" {
    body='{"digest":"sha256:0000000000000000000000000000000000000000000000000000000000000000","image":"fiestaboard/fiestaboard:latest"}'
    len=${#body}
    req=$(printf 'POST /rollback HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n\r\n%s' "$len" "$body")
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 401 Unauthorized" ]]
}

@test "POST /rollback rejects invalid digest (no docker call)" {
    body='{"digest":"not-a-digest","image":"fiestaboard/fiestaboard:latest"}'
    len=${#body}
    req=$(printf 'POST /rollback HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: %d\r\n\r\n%s' "$len" "$body")
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 400 Bad Request" ]]
    [[ "$out" == *'"error":"invalid_digest"'* ]]
    # Must not have called `docker tag` or `docker compose up`.
    if [ -f "${SANDBOX}/docker.calls" ]; then
        ! grep -q '^tag ' "${SANDBOX}/docker.calls"
        ! grep -q 'force-recreate' "${SANDBOX}/docker.calls"
    fi
}

@test "POST /rollback rejects shell-injection image references" {
    body='{"digest":"sha256:0000000000000000000000000000000000000000000000000000000000000000","image":"foo;rm -rf /"}'
    len=${#body}
    req=$(printf 'POST /rollback HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: %d\r\n\r\n%s' "$len" "$body")
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 400 Bad Request" ]]
    [[ "$out" == *'"error":"invalid_image"'* ]]
}

@test "POST /rollback with valid body retags digest and force-recreates" {
    digest='sha256:1111111111111111111111111111111111111111111111111111111111111111'
    body="{\"digest\":\"${digest}\",\"image\":\"fiestaboard/fiestaboard:latest\"}"
    len=${#body}
    req=$(printf 'POST /rollback HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: %d\r\n\r\n%s' "$len" "$body")
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 202 Accepted" ]]
    [[ "$out" == *"\"target_digest\":\"${digest}\""* ]]

    # Wait for the background worker to finish writing state.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        if [ -f "${SANDBOX}/state/last-update.json" ] && \
           grep -q '"status":"rolled_back"' "${SANDBOX}/state/last-update.json"; then
            break
        fi
        sleep 1
    done

    # Heart of the rollback: retag target digest onto image ref, then
    # force-recreate the service so it picks the rollback target up.
    grep -q "tag ${digest} fiestaboard/fiestaboard:latest" "${SANDBOX}/docker.calls"
    grep -q "up -d --no-deps --force-recreate fiestaboard" "${SANDBOX}/docker.calls"
    grep -q '"status":"rolled_back"' "${SANDBOX}/state/last-update.json"
    grep -q "\"target_digest\":\"${digest}\"" "${SANDBOX}/state/last-update.json"
}

# ---- /update : in-progress bookkeeping ------------------------------------

@test "POST /update writes in_progress state immediately" {
    # Even before the background worker finishes, the state file should
    # reflect that an attempt is underway so the UI can show progress.
    req=$'POST /update HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    send "$req" >/dev/null
    [ -f "${SANDBOX}/state/last-update.json" ]
    grep -q '"status":"in_progress"' "${SANDBOX}/state/last-update.json"
    grep -q '"previous_digest":"sha256:abc123"' "${SANDBOX}/state/last-update.json"
}
