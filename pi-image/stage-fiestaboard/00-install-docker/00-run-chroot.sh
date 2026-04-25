#!/bin/bash -e
# Install Docker + Compose using the official convenience script.
# Runs inside the rootfs chroot.

# Bring the package index up to date and install dependencies.
apt-get update
apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    avahi-daemon

# Install Docker Engine via the official Docker apt repo (stable channel).
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
    -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian ${CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y --no-install-recommends \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

# Add the default user to the docker group so they don't need sudo.
usermod -aG docker "${FIRST_USER_NAME}"

# Enable Docker on boot.
systemctl enable docker

# Clean up to keep the image small.
apt-get clean
rm -rf /var/lib/apt/lists/*
