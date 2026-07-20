---
sidebar_position: 1
description: "Deploy FiestaBoard on a Raspberry Pi 3B+, Zero 2W, or Pi 4 to run your split-flap display dashboard 24/7."
keywords: [FiestaBoard Raspberry Pi, Pi deployment, Raspberry Pi 4, Pi Zero 2W, self-hosted, split-flap Pi]
---

# Raspberry Pi Deployment

Deploy FiestaBoard on a Raspberry Pi for a dedicated, always-on dashboard controller.

## Compatible Models

| Model | Architecture | Status |
|-------|-------------|--------|
| Raspberry Pi 3B+ | `linux/arm64` | Supported (requires 64-bit OS) |
| Raspberry Pi Zero 2 W | `linux/arm64` | Supported (requires 64-bit OS) |
| Raspberry Pi 4 | `linux/arm64` | Supported |
| Raspberry Pi 5 | `linux/arm64` | Supported |

## Prerequisites

- Raspberry Pi with Raspberry Pi OS (Bookworm or later)
- At least 2GB of RAM recommended
- Docker and Docker Compose installed
- Network access to your board

## Installing Docker on Raspberry Pi

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to the docker group
sudo usermod -aG docker $USER

# Log out and back in, then verify
docker --version
```

## Setting Up FiestaBoard

```bash
# Clone the repository
git clone https://github.com/Fiestaboard/FiestaBoard.git
cd FiestaBoard

# Create your configuration
cp env.example .env
# Edit .env with your API keys

# Start FiestaBoard
docker compose up -d --build
```

:::info Build Times
The first build on a Raspberry Pi will take longer than on a desktop computer. Expect 10-20 minutes depending on your Pi model and SD card speed.
:::

## Using Pre-Built ARM Images

For faster setup, use the pre-built images from Docker Hub:

```bash
docker compose -f docker-compose.hub.yml up -d
```

This skips the build step entirely and pulls ready-to-run ARM images.

## Multi-Architecture Builds

Every release automatically builds images for both `linux/amd64` and `linux/arm64`, so Raspberry Pi is always supported out of the box.

> **Note:** 32-bit ARM (`linux/arm/v7`) is no longer supported because Node.js dropped ARM32v7 support in v20+. Please use a 64-bit Raspberry Pi OS.

## Performance Tips

- **Use a fast SD card** - Class 10 or higher, ideally A2-rated
- **Consider USB boot** - Boot from USB SSD for better performance
- **Monitor temperature** - Use a heatsink or fan case for sustained operation
- **Set appropriate refresh intervals** - Don't refresh more frequently than needed

```bash
# In .env, 60 seconds is usually sufficient
REFRESH_INTERVAL_SECONDS=60
```

## Auto-Start on Boot

To have FiestaBoard start automatically when your Pi boots:

```bash
# Enable Docker to start on boot
sudo systemctl enable docker

# Create a systemd service for FiestaBoard
sudo tee /etc/systemd/system/fiestaboard.service << 'EOF'
[Unit]
Description=FiestaBoard
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/pi/FiestaBoard
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
EOF

# Enable the service
sudo systemctl enable fiestaboard
```

## Accessing From Other Devices

Once FiestaBoard is running on your Pi, you can access it from any device on the same network:

- **http://fiestaboard.local:4420** — works on most home networks via mDNS/Bonjour. No need to remember the Pi's IP address.
- **http://&lt;pi-ip-address&gt;:4420** — use this if `.local` addresses don't work on your network. Find your Pi's IP with `hostname -I`.

To change the advertised hostname, set `MDNS_HOSTNAME` in your `.env` file (default: `fiestaboard`, which becomes `fiestaboard.local`).

## Next Steps

- [Production Deployment](/docs/deployment/production) - Production best practices
- [Docker Setup](/docs/setup/docker-setup) - Docker architecture details
