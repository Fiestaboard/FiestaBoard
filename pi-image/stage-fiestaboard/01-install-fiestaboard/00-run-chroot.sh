#!/bin/bash -e
# Lay down the FiestaBoard install directory in the rootfs.
# pi-gen will tar this rootfs into the final .img.

INSTALL_DIR="${ROOTFS_DIR}/opt/fiestaboard"
mkdir -p "$INSTALL_DIR"

install -m 0644 files/docker-compose.yml "${INSTALL_DIR}/docker-compose.yml"
install -m 0644 files/env.template       "${INSTALL_DIR}/env.template"

# firstboot.sh lives one directory up at pi-image/.  pi-gen substages run
# from inside the substage dir, so navigate accordingly.
install -m 0755 ../../firstboot.sh "${INSTALL_DIR}/firstboot.sh"

# systemd unit
install -m 0644 files/fiestaboard.service \
    "${ROOTFS_DIR}/etc/systemd/system/fiestaboard.service"

on_chroot <<'EOF'
systemctl enable fiestaboard.service

# 1 GB swap file — Pi 3B (1 GB RAM) needs it for image pulls + Next.js.
if [ ! -f /var/swap ]; then
    fallocate -l 1G /var/swap || dd if=/dev/zero of=/var/swap bs=1M count=1024
    chmod 600 /var/swap
    mkswap /var/swap
    if ! grep -q "/var/swap" /etc/fstab; then
        echo "/var/swap none swap sw 0 0" >> /etc/fstab
    fi
fi

# Pre-pull images on first boot would be ideal, but pi-gen builds in a
# chroot without networking guarantees.  We skip pre-pull and let the
# systemd unit do it on first real boot.
EOF
