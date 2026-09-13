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
    # Matched in two parts rather than as one literal: the flag list between
    # --force-recreate and the service name is allowed to grow (it gained
    # --pull never), and pinning the exact string makes an unrelated flag
    # addition look like a broken recreate.
    grep -E "up -d --no-deps --force-recreate" "${SANDBOX}/docker.calls" | grep -q "fiestaboard"
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

# ---- /update : image pruning ------------------------------------------------

@test "successful update prunes stale dangling images but keeps rollback target" {
    # Replace the mock docker with one that exposes two dangling images:
    #   staleimg   → full ID sha256:stale... (older generation, safe to remove)
    #   rollbackimg → full ID sha256:abc123  (the pre-update image, must be kept)
    # FU_BEFORE_DIGEST is set from `docker inspect --format '{{.Image}}' fiestaboard`
    # which the mock returns as sha256:abc123, so rollbackimg must be spared.
    cat >"${SANDBOX}/docker" <<'SH'
#!/bin/sh
echo "$@" >> "${SANDBOX}/docker.calls"
case "$1" in
    inspect)
        case "$3" in
            *Config.Image*) echo "fiestaboard/fiestaboard:latest" ;;
            *Id*)
                case "$4" in
                    staleimg)    echo "sha256:stalestalestalestaledead000000000000000000000000000000000000000" ;;
                    rollbackimg) echo "sha256:abc123" ;;
                    *)           echo "" ;;
                esac
                ;;
            *Image*) echo "sha256:abc123" ;;
            *)       echo "" ;;
        esac
        ;;
    image)
        case "$2" in
            ls) printf 'staleimg\nrollbackimg\n' ;;
            rm) exit 0 ;;
        esac
        ;;
    compose|tag) exit 0 ;;
    *) exit 0 ;;
esac
SH
    chmod +x "${SANDBOX}/docker"

    req=$'POST /update HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    send "$req" >/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        if [ -f "${SANDBOX}/state/last-update.json" ] && \
           grep -q '"status":"success"' "${SANDBOX}/state/last-update.json"; then
            break
        fi
        sleep 1
    done

    grep -q '"status":"success"' "${SANDBOX}/state/last-update.json"
    # Stale image (not the rollback target) must be removed.
    grep -q 'image rm staleimg' "${SANDBOX}/docker.calls"
    # Rollback target must NOT be removed.
    ! grep -q 'image rm rollbackimg' "${SANDBOX}/docker.calls"
}

# ---- /hdmi : kiosk enable/disable ------------------------------------------

@test "GET /hdmi/status with no state file → unknown" {
    req=$'GET /hdmi/status HTTP/1.1\r\nHost: x\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 200 OK" ]]
    [[ "$out" == *'"status":"unknown"'* ]]
}

@test "GET /hdmi/status returns the persisted state" {
    mkdir -p "${FIESTAUPDATER_STATE_DIR}"
    printf '%s' '{"status":"enabled","action":"enable"}' > "${FIESTAUPDATER_STATE_DIR}/hdmi.json"
    req=$'GET /hdmi/status HTTP/1.1\r\nHost: x\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 200 OK" ]]
    [[ "$out" == *'"status":"enabled"'* ]]
}

@test "POST /hdmi/enable requires auth" {
    req=$'POST /hdmi/enable HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 401 Unauthorized" ]]
}

@test "POST /hdmi/enable with valid token → 202 and runs the host-namespace helper" {
    export FIESTAUPDATER_HDMI_SCRIPT="${SANDBOX}/setup.sh"
    printf '%s\n' '#!/bin/bash' 'echo setup' > "${FIESTAUPDATER_HDMI_SCRIPT}"
    req=$'POST /hdmi/enable HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 202 Accepted" ]]
    [[ "$out" == *'"action":"hdmi_enable"'* ]]
    sleep 1
    # The worker must run a privileged host-namespace helper (nsenter into
    # PID 1) using the service image, with the script fed over stdin.
    grep -q -- "--privileged" "${SANDBOX}/docker.calls"
    grep -q -- "--pid=host" "${SANDBOX}/docker.calls"
    grep -q -- "nsenter" "${SANDBOX}/docker.calls"
    grep -q -- "fiestaboard/fiestaboard:latest" "${SANDBOX}/docker.calls"
    # Success is persisted for GET /hdmi/status.
    grep -q '"status":"enabled"' "${FIESTAUPDATER_STATE_DIR}/hdmi.json"
}

@test "POST /hdmi/disable passes --disable to the setup script" {
    export FIESTAUPDATER_HDMI_SCRIPT="${SANDBOX}/setup.sh"
    printf '%s\n' '#!/bin/bash' 'echo setup' > "${FIESTAUPDATER_HDMI_SCRIPT}"
    req=$'POST /hdmi/disable HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 202 Accepted" ]]
    sleep 1
    grep -q -- "--disable" "${SANDBOX}/docker.calls"
    grep -q '"status":"disabled"' "${FIESTAUPDATER_STATE_DIR}/hdmi.json"
}

@test "POST /hdmi/enable with missing setup script → 500" {
    export FIESTAUPDATER_HDMI_SCRIPT="${SANDBOX}/does-not-exist.sh"
    req=$'POST /hdmi/enable HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 500 Internal Server Error" ]]
    [[ "$out" == *hdmi_script_missing* ]]
}

# ---- /install --------------------------------------------------------------
#
# Installs a NAMED TAG. This is what lets a box switch release channels
# without anyone editing a compose file — which matters because the compose
# file is mounted read-only here, and on the Pi image the app container does
# not mount it at all.
#
# Mechanically it is /rollback's move with a pull in front: fetch the tag,
# retag it onto whatever reference the compose file names, recreate.

@test "POST /install with no Authorization → 401" {
    req=$'POST /install HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n'
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 401 Unauthorized" ]]
}

@test "POST /install with wrong bearer token → 401" {
    body='{"image":"fiestaboard/fiestaboard","tag":"9.0.0-beta.2"}'
    req=$'POST /install HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer nope\r\nContent-Length: '"${#body}"$'\r\n\r\n'"$body"
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 401 Unauthorized" ]]
}

@test "POST /install pulls the requested tag and recreates the service" {
    body='{"image":"fiestaboard/fiestaboard","tag":"9.0.0-beta.2"}'
    req=$'POST /install HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: '"${#body}"$'\r\n\r\n'"$body"
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 202 Accepted" ]]
    [[ "$out" == *'"status":"queued"'* ]]
    [[ "$out" == *'"action":"install"'* ]]
    sleep 1
    grep -q "pull fiestaboard/fiestaboard:9.0.0-beta.2" "${SANDBOX}/docker.calls"
    # Matched in two parts rather than as one literal: the flag list between
    # --force-recreate and the service name is allowed to grow (it gained
    # --pull never), and pinning the exact string makes an unrelated flag
    # addition look like a broken recreate.
    grep -E "up -d --no-deps --force-recreate" "${SANDBOX}/docker.calls" | grep -q "fiestaboard"
}

@test "POST /install retags onto the compose reference, not one the caller picks" {
    # The security property: the caller says which tag to FETCH, never which
    # local reference to overwrite. That comes from the running container, so
    # a compromised or buggy caller cannot retag some unrelated image.
    body='{"image":"fiestaboard/fiestaboard","tag":"9.0.0-beta.2","target":"evil/image:latest"}'
    req=$'POST /install HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: '"${#body}"$'\r\n\r\n'"$body"
    send "$req" >/dev/null
    sleep 1
    grep -q "tag fiestaboard/fiestaboard:9.0.0-beta.2 fiestaboard/fiestaboard:latest" "${SANDBOX}/docker.calls"
    ! grep -q "evil/image" "${SANDBOX}/docker.calls"
}

@test "POST /install rejects a bogus image reference" {
    body='{"image":"bad;rm -rf /","tag":"9.0.0-beta.2"}'
    req=$'POST /install HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: '"${#body}"$'\r\n\r\n'"$body"
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 400 Bad Request" ]]
    [[ "$out" == *'"error":"invalid_image"'* ]]
}

@test "POST /install rejects a bogus tag" {
    body='{"image":"fiestaboard/fiestaboard","tag":"latest;reboot"}'
    req=$'POST /install HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: '"${#body}"$'\r\n\r\n'"$body"
    out=$(send "$req")
    [[ "$(status_of "$out")" == "HTTP/1.1 400 Bad Request" ]]
    [[ "$out" == *'"error":"invalid_tag"'* ]]
}

@test "POST /install records success in last-update state" {
    body='{"image":"fiestaboard/fiestaboard","tag":"9.0.0-beta.2"}'
    req=$'POST /install HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: '"${#body}"$'\r\n\r\n'"$body"
    send "$req" >/dev/null
    sleep 1
    # "success" and not a new status word, so the web UI's existing
    # update-overlay polling recognises the outcome unchanged.
    grep -q '"status":"success"' "${SANDBOX}/state/last-update.json"
    grep -q '"action":"install"' "${SANDBOX}/state/last-update.json"
}

@test "POST /install writes status=failed when the pull fails" {
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
    pull) exit 1 ;;
    *)    exit 0 ;;
esac
SH
    chmod +x "${SANDBOX}/docker"
    body='{"image":"fiestaboard/fiestaboard","tag":"9.0.0-beta.2"}'
    req=$'POST /install HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: '"${#body}"$'\r\n\r\n'"$body"
    send "$req" >/dev/null
    sleep 1
    grep -q '"status":"failed"' "${SANDBOX}/state/last-update.json"
    grep -q '"error":"pull_failed"' "${SANDBOX}/state/last-update.json"
    # A failed pull must not touch the running container.
    ! grep -q "force-recreate" "${SANDBOX}/docker.calls"
}

# ---- pull_policy: always defeats a retag -----------------------------------
#
# Found on a real FiestaPi: POST /install reported success, every step exited
# 0, and the box stayed on stable.
#
# The shipped compose files set `pull_policy: always` (pi-image
# docker-compose.yml:11, docker-compose.hub.yml:11). `docker compose up
# --force-recreate` honours it, so the recreate RE-PULLS the tag from the
# registry and overwrites the local retag. Reproduced minimally: retag
# alpine:3.20 onto alpine:3.21, recreate, and the container comes back as
# 3.21 — the retag silently reverted.
#
# /install and /rollback both already hold the exact image they want, so
# compose must not refetch. /update is deliberately unchanged: it WANTS the
# newest image.

@test "POST /install recreates with --pull never so the retag survives" {
    body='{"image":"fiestaboard/fiestaboard","tag":"9.0.0-beta.3"}'
    req=$'POST /install HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: '"${#body}"$'\r\n\r\n'"$body"
    send "$req" >/dev/null
    sleep 1
    grep -E "up -d --no-deps --force-recreate" "${SANDBOX}/docker.calls" | grep -q -- "--pull never"
}

@test "POST /rollback recreates with --pull never so the retag survives" {
    digest="sha256:$(printf 'a%.0s' $(seq 1 64))"
    body="{\"digest\":\"${digest}\",\"image\":\"fiestaboard/fiestaboard:latest\"}"
    req=$'POST /rollback HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: '"${#body}"$'\r\n\r\n'"$body"
    send "$req" >/dev/null
    sleep 1
    grep -E "up -d --no-deps --force-recreate" "${SANDBOX}/docker.calls" | grep -q -- "--pull never"
}

@test "POST /update still pulls — it wants the newest image, not a held one" {
    req=$'POST /update HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer test-token-abc\r\nContent-Length: 0\r\n\r\n'
    send "$req" >/dev/null
    sleep 1
    grep -q "pull fiestaboard" "${SANDBOX}/docker.calls"
    ! grep -E "up -d --no-deps fiestaboard" "${SANDBOX}/docker.calls" | grep -q -- "--pull never"
}
