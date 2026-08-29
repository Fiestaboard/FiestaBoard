#!/bin/bash
# FiestaPi HDMI kiosk — retrofit installer for already-deployed Pis.
#
# New FiestaPi images ship the kiosk baked in (pi-image/stage-fiestaboard/
# 02-hdmi-kiosk/), but fiestaupdater only updates the FiestaBoard *container*,
# never the host OS — so Pis flashed before the kiosk existed need this
# one-time script. Run it on the Pi over SSH:
#
#     curl -fsSL https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/scripts/fiestapi-hdmi-setup.sh | sudo bash
#
# It is idempotent and mirrors the image stage exactly: installs cage +
# Chromium + seatd, creates the unprivileged kiosk user, lays down the
# systemd unit and the wait-for-server script, drops the fiestapi-hdmi.txt
# enable flag on the boot partition, and starts the kiosk. Re-running is
# safe. To turn the kiosk off later:
#
#     sudo /opt/fiestaboard/fiestapi-hdmi-setup.sh --disable
#
# (or just delete /boot/firmware/fiestapi-hdmi.txt and reboot).
#
# KEEP IN SYNC with pi-image/stage-fiestaboard/02-hdmi-kiosk/ — the unit
# and wait script below are copies of the files the image stage installs.

set -euo pipefail

BOOT_FLAG="/boot/firmware/fiestapi-hdmi.txt"
UNIT="/etc/systemd/system/fiestapi-kiosk.service"
WAIT="/opt/fiestaboard/kiosk-wait.sh"

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must run as root: sudo $0" >&2
    exit 1
fi

if [ "${1:-}" = "--disable" ]; then
    rm -f "$BOOT_FLAG"
    systemctl stop fiestapi-kiosk.service 2>/dev/null || true
    echo "HDMI kiosk disabled (removed $BOOT_FLAG). It will not start on future boots."
    echo "Re-enable any time with: sudo touch $BOOT_FLAG && sudo reboot"
    exit 0
fi

if [ ! -d /boot/firmware ]; then
    echo "This does not look like a Raspberry Pi OS install (/boot/firmware missing)." >&2
    exit 1
fi

echo "Installing kiosk packages (cage, chromium, seatd)…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends cage chromium seatd

echo "Creating kiosk user…"
if ! id kiosk >/dev/null 2>&1; then
    useradd --create-home --shell /usr/sbin/nologin kiosk
fi
usermod -aG video,render,input kiosk

echo "Installing wait script…"
mkdir -p /opt/fiestaboard
cat > "$WAIT" <<'WAIT_EOF'
#!/bin/bash
# Block until the FiestaBoard web server answers on localhost so the kiosk
# browser never opens onto a connection-refused page during boot. First
# boots pull Docker images and can legitimately take minutes; we wait up
# to 15, then let Chromium start anyway — the app's own boot splash and
# retry logic take over from there.
set -u

DEADLINE=$((SECONDS + 900))
until curl -fsS -o /dev/null --max-time 5 "http://localhost:4420/api/health"; do
    if [ "$SECONDS" -ge "$DEADLINE" ]; then
        echo "kiosk-wait: FiestaBoard not up after 15 min; starting browser anyway" >&2
        exit 0
    fi
    sleep 3
done
WAIT_EOF
chmod 0755 "$WAIT"

echo "Installing systemd unit…"
cat > "$UNIT" <<'UNIT_EOF'
[Unit]
Description=FiestaPi HDMI kiosk (FiestaPanel on the connected screen)
Documentation=https://fiestaboard.app/docs/features/fiestapanel
# Opt-in: the kiosk (and its ~200 MB of Chromium RSS) only runs when the
# user dropped the flag file on the boot partition. Delete the file and
# reboot to reclaim the memory — important on the 1 GB Pi 3B.
ConditionPathExists=/boot/firmware/fiestapi-hdmi.txt
After=fiestaboard.service systemd-user-sessions.service
Wants=fiestaboard.service

[Service]
Type=simple
User=kiosk
# The wait script blocks until the FiestaBoard nginx answers so Chromium
# never paints a connection-refused page on boot.
ExecStartPre=/opt/fiestaboard/kiosk-wait.sh
# cage = single-window Wayland kiosk compositor; Chromium renders the
# reserved /p/display URL, which follows whichever panel the user marks
# as "Display output" in Settings → Hardware → FiestaPanel.
ExecStart=/usr/bin/cage -d -- /usr/bin/chromium \
    --kiosk \
    --ozone-platform=wayland \
    --no-first-run \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=TranslateUI \
    --check-for-update-interval=31536000 \
    --user-data-dir=/home/kiosk/.chromium-kiosk \
    http://localhost:4420/p/display
Restart=always
RestartSec=5

# Give cage a real seat + VT, per the cage systemd deployment guide.
PAMName=login
TTYPath=/dev/tty7
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=yes
StandardInput=tty-fail
StandardOutput=journal
StandardError=journal
UtmpIdentifier=tty7
UtmpMode=user

[Install]
# Pi OS Lite boots to multi-user.target — graphical.target never fires here.
WantedBy=multi-user.target
UNIT_EOF

echo "Enabling…"
touch "$BOOT_FLAG"
systemctl daemon-reload
systemctl enable fiestapi-kiosk.service

# Keep a local copy so --disable works without re-downloading.
SELF_COPY="/opt/fiestaboard/fiestapi-hdmi-setup.sh"
if [ -f "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "$SELF_COPY" ]; then
    cp "${BASH_SOURCE[0]}" "$SELF_COPY" && chmod 0755 "$SELF_COPY" || true
fi

echo "Starting the kiosk…"
systemctl restart fiestapi-kiosk.service || true

cat <<'DONE_EOF'

HDMI kiosk installed and enabled.

The connected screen now shows the reserved /p/display FiestaPanel URL.
Next: in FiestaBoard open Settings → Hardware → FiestaPanel, create a
panel (pick this screen's size), and turn on "Display output" for it.
Exactly one panel holds that role at a time — switch it any time from
the app and the screen follows.

Disable later with:  sudo /opt/fiestaboard/fiestapi-hdmi-setup.sh --disable
DONE_EOF
