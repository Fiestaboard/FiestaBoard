#!/bin/bash
# First-boot bootstrap for FiestaPi.
# Idempotent: safe to run on every boot (the systemd unit does this via
# ExecStartPre).  All it actually does on subsequent boots is no-op.
set -eu

INSTALL_DIR=/opt/fiestaboard
ENV_FILE="${INSTALL_DIR}/.env"
TOKEN_PLACEHOLDER="__GENERATED_AT_FIRST_BOOT__"

# Boot-partition WiFi config file — users can drop this onto the FAT32 boot
# partition from any OS after flashing, before first power-on.
WIFI_CONFIG_FILE="/boot/firmware/fiestapi-wifi.txt"

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

# ── WiFi provisioning via boot-partition file ─────────────────────────────
# If /boot/firmware/fiestapi-wifi.txt exists, configure the WiFi connection
# and then delete the file so the credentials don't sit on the FAT partition.
#
# Expected file format (plain text, one key=value per line):
#   SSID=MyNetwork
#   PASSWORD=MyPassword
#
if [ -f "$WIFI_CONFIG_FILE" ]; then
    WIFI_SSID=""
    WIFI_PASSWORD=""

    while IFS='=' read -r key value; do
        # Strip leading/trailing whitespace and ignore comment lines.
        key="$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        value="$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        case "$key" in
            SSID)     WIFI_SSID="$value" ;;
            PASSWORD) WIFI_PASSWORD="$value" ;;
        esac
    done < "$WIFI_CONFIG_FILE"

    # Remove the file immediately — credentials should not persist on the
    # readable FAT partition any longer than necessary.
    rm -f "$WIFI_CONFIG_FILE"

    if [ -n "$WIFI_SSID" ]; then
        if [ -n "$WIFI_PASSWORD" ]; then
            nmcli device wifi connect "$WIFI_SSID" password "$WIFI_PASSWORD" \
                2>&1 | logger -t fiestapi-firstboot || true
        else
            # Open network (no password).
            nmcli device wifi connect "$WIFI_SSID" \
                2>&1 | logger -t fiestapi-firstboot || true
        fi
        logger -t fiestapi-firstboot "WiFi configured for SSID: ${WIFI_SSID}"
    else
        logger -t fiestapi-firstboot \
            "fiestapi-wifi.txt found but SSID was empty — skipping WiFi setup"
    fi
fi

exit 0
