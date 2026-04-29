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
    compose)
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
