#!/bin/bash -e
# HDMI kiosk: boot the Pi straight into the FiestaPanel viewer on a
# connected screen. Opt-in at flash time (or any time after) by dropping
# `fiestapi-hdmi.txt` on the boot partition — the systemd unit's
# ConditionPathExists keeps Chromium entirely out of memory otherwise.
# Runs on the HOST (not in chroot); see 01-install-fiestaboard/00-run.sh.

install -m 0755 files/kiosk-wait.sh "${ROOTFS_DIR}/opt/fiestaboard/kiosk-wait.sh"
install -m 0644 files/fiestapi-kiosk.service \
    "${ROOTFS_DIR}/etc/systemd/system/fiestapi-kiosk.service"

on_chroot <<'EOF'
# Dedicated unprivileged user for the kiosk session. video/render/input
# give cage direct access to the GPU and (absent) input devices.
if ! id kiosk >/dev/null 2>&1; then
    useradd --create-home --shell /usr/sbin/nologin kiosk
fi
usermod -aG video,render,input kiosk

# The unit is enabled unconditionally; ConditionPathExists on the boot
# partition flag file decides at boot whether it actually runs.
systemctl enable fiestapi-kiosk.service
EOF
