#!/bin/bash
# Reclaim our base mDNS hostname if avahi-daemon has renamed itself due to a
# past conflict (e.g. advertising as fiestapi-2.local instead of fiestapi.local).
#
# Why this exists: avahi auto-renames on hostname collision (common when a
# previously-flashed FiestaPi held the name and then disappeared, or during
# a brief network blip).  Once renamed, avahi NEVER retries the bare name on
# its own — even after the conflict is long gone.  A restart makes it try
# again; if the conflict is still active it simply renames itself again, so
# this is safe to run repeatedly.

set -eu

EXPECTED="$(hostname).local"

# Ask avahi over D-Bus what FQDN it's currently advertising.  This is more
# reliable than parsing `systemctl status` output and avoids needing
# avahi-utils (avahi-resolve) on the image.
CURRENT="$(dbus-send --system --print-reply --reply-timeout=5000 \
    --dest=org.freedesktop.Avahi / \
    org.freedesktop.Avahi.Server.GetHostNameFqdn 2>/dev/null \
    | awk -F'"' '/string/ {print $2; exit}')"

# If we couldn't read avahi's state, do nothing rather than restart blindly.
if [ -z "$CURRENT" ] || [ "$CURRENT" = "$EXPECTED" ]; then
    exit 0
fi

logger -t fiestapi-heal-mdns \
    "avahi advertising as ${CURRENT}, expected ${EXPECTED} — restarting to reclaim"
systemctl restart avahi-daemon
