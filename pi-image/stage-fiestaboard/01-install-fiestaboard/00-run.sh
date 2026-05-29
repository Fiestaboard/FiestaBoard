#!/bin/bash -e
# Lay down the FiestaBoard install directory in the rootfs.
# pi-gen will tar this rootfs into the final .img.
# Runs on the HOST (not in chroot) so we have access to ${ROOTFS_DIR} and files/.

INSTALL_DIR="${ROOTFS_DIR}/opt/fiestaboard"
mkdir -p "$INSTALL_DIR"

install -m 0644 files/docker-compose.yml "${INSTALL_DIR}/docker-compose.yml"
install -m 0644 files/env.template       "${INSTALL_DIR}/env.template"
install -m 0755 files/firstboot.sh       "${INSTALL_DIR}/firstboot.sh"
install -m 0755 files/heal-mdns.sh       "${INSTALL_DIR}/heal-mdns.sh"

# systemd units
install -m 0644 files/fiestaboard.service \
    "${ROOTFS_DIR}/etc/systemd/system/fiestaboard.service"
install -m 0644 files/fiestapi-heal-mdns.service \
    "${ROOTFS_DIR}/etc/systemd/system/fiestapi-heal-mdns.service"
install -m 0644 files/fiestapi-heal-mdns.timer \
    "${ROOTFS_DIR}/etc/systemd/system/fiestapi-heal-mdns.timer"

on_chroot <<'EOF'
# ── Docker installation ───────────────────────────────────────────────────
# Install Docker CE from Docker's official apt repo so docker.service exists
# before fiestaboard.service tries to start it.
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
    -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian trixie stable" \
    | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -qq
apt-get install -y --no-install-recommends \
    docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Enable Docker and FiestaBoard to start on boot.
systemctl enable docker
systemctl enable fiestaboard.service

# Periodic self-heal for the fiestapi.local mDNS hostname.  See heal-mdns.sh
# for why this is needed (avahi never retries the bare name after a rename).
systemctl enable fiestapi-heal-mdns.timer

# Add the default user (uid 1000) to the docker group.
FIRST_USER="$(getent passwd 1000 | cut -d: -f1)"
[ -n "$FIRST_USER" ] && usermod -aG docker "$FIRST_USER" || true

# 1 GB swap file — Pi 3B (1 GB RAM) needs it for image pulls + Next.js.
if [ ! -f /var/swap ]; then
    fallocate -l 1G /var/swap || dd if=/dev/zero of=/var/swap bs=1M count=1024
    chmod 600 /var/swap
    mkswap /var/swap
    if ! grep -q "/var/swap" /etc/fstab; then
        echo "/var/swap none swap sw 0 0" >> /etc/fstab
    fi
fi
EOF
