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

# Docker is pre-installed during the image build; nothing to do here.

# Materialize .env from template on first run.
if [ ! -f "$ENV_FILE" ]; then
    cp "${INSTALL_DIR}/env.template" "$ENV_FILE"
fi

# Generate the shared bearer token if the placeholder is still there.
# Format: 32 random bytes encoded as lowercase hexadecimal (64 chars, 256-bit entropy).
if grep -q "$TOKEN_PLACEHOLDER" "$ENV_FILE"; then
    TOKEN="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    if ! printf '%s' "$TOKEN" | grep -Eq '^[0-9a-f]{64}$'; then
        echo "firstboot: token generation failed sanity check (expected 64 lowercase hex chars)" >&2
        exit 1
    fi
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
#   COUNTRY=US        # optional, ISO-3166 alpha-2; defaults to US
#
# NOTE: On a fresh Raspberry Pi OS install the WiFi radio is rfkill-blocked
# until a wireless regulatory country is set.  Without this, `nmcli device
# wifi connect` fails with "Error: Failed to add/activate new connection:
# WiFi is currently blocked by rfkill" and the user has to drop into
# raspi-config manually.  We unblock + set the country *before* attempting
# the connection.
if [ -f "$WIFI_CONFIG_FILE" ]; then
    WIFI_SSID=""
    WIFI_PASSWORD=""
    WIFI_COUNTRY=""

    while IFS='=' read -r key value; do
        # Strip leading/trailing whitespace and ignore comment lines.
        key="$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        value="$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        [[ -z "$key" && -z "$value" ]] && continue
        [[ -z "$key" || "$key" =~ ^# ]] && continue
        case "$key" in
            SSID)     WIFI_SSID="$value" ;;
            PASSWORD) WIFI_PASSWORD="$value" ;;
            COUNTRY)  WIFI_COUNTRY="$value" ;;
        esac
    done < "$WIFI_CONFIG_FILE"

    # Remove the file immediately — credentials should not persist on the
    # readable FAT partition any longer than necessary.
    if command -v shred >/dev/null 2>&1; then
        shred -u "$WIFI_CONFIG_FILE" || true
    else
        rm -f "$WIFI_CONFIG_FILE"
    fi

    if [ -n "$WIFI_SSID" ]; then
        # Default to US if the user didn't specify a country.  The radio
        # stays rfkill-blocked until a country is set, so a default is
        # better than failing silently.  Uppercase to match ISO-3166.
        WIFI_COUNTRY="${WIFI_COUNTRY:-US}"
        WIFI_COUNTRY="$(echo "$WIFI_COUNTRY" | tr '[:lower:]' '[:upper:]')"

        # Set the WiFi regulatory domain.  raspi-config's nonint helper
        # writes the country to wpa_supplicant.conf / NetworkManager,
        # calls `iw reg set`, and unblocks rfkill in one shot.
        if command -v raspi-config >/dev/null 2>&1; then
            raspi-config nonint do_wifi_country "$WIFI_COUNTRY" \
                2>&1 | logger -t fiestapi-firstboot || true
        fi
        # Belt-and-braces: unblock rfkill directly in case raspi-config
        # isn't available or didn't take effect this boot.
        if command -v rfkill >/dev/null 2>&1; then
            rfkill unblock wifi 2>&1 | logger -t fiestapi-firstboot || true
        fi
        logger -t fiestapi-firstboot \
            "WiFi country set to ${WIFI_COUNTRY}; rfkill unblocked"

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

# ── Wait for actual connectivity ──────────────────────────────────────────
# The systemd unit no longer waits for network-online.target so that this
# script can own bringing the network up on WiFi-only first boots. Block
# here until NetworkManager reports at least one connection is fully online
# (DHCP + DNS, not just associated) or 60 s elapses. If we time out we still
# proceed — fiestaboard.service has Restart=on-failure and will retry the
# pull once the link comes up.
if command -v nm-online >/dev/null 2>&1; then
    # Run nm-online standalone (not in a pipe) so its exit code is the one
    # we branch on — piping to logger would mask it and the || would only
    # ever fire on logger's exit, which is effectively never.
    if nm-online --timeout=60 >/dev/null 2>&1; then
        logger -t fiestapi-firstboot "nm-online: connectivity confirmed"
    else
        logger -t fiestapi-firstboot \
            "nm-online timed out after 60s; proceeding without confirmed connectivity"
    fi
fi

exit 0
