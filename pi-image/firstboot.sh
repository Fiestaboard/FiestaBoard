#!/bin/bash
# First-boot bootstrap for FiestaPi.
# Idempotent: safe to run on every boot (the systemd unit does this via
# ExecStartPre).  All it actually does on subsequent boots is no-op.
set -eu

INSTALL_DIR=/opt/fiestaboard
ENV_FILE="${INSTALL_DIR}/.env"
TOKEN_PLACEHOLDER="__GENERATED_AT_FIRST_BOOT__"

mkdir -p "${INSTALL_DIR}/data" "${INSTALL_DIR}/external_plugins"

# Materialize .env from template on first run.
if [ ! -f "$ENV_FILE" ]; then
    cp "${INSTALL_DIR}/env.template" "$ENV_FILE"
fi

# Generate the shared bearer token if the placeholder is still there.
if grep -q "$TOKEN_PLACEHOLDER" "$ENV_FILE"; then
    TOKEN="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    sed -i "s|${TOKEN_PLACEHOLDER}|${TOKEN}|" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
fi

exit 0
