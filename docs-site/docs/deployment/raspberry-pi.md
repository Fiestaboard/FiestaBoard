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
| Raspberry Pi 3B+ | `linux/arm/v7` | Supported |
| Raspberry Pi Zero 2 W | `linux/arm/v7` | Supported |
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
docker-compose up -d --build
```

:::info Build Times
The first build on a Raspberry Pi will take longer than on a desktop computer. Expect 10-20 minutes depending on your Pi model and SD card speed.
:::

## Using Pre-Built ARM Images

For faster setup, use the pre-built images from Docker Hub:

```bash
docker-compose -f docker-compose.hub.yml up -d
```

This skips the build step entirely and pulls ready-to-run ARM images.

## Pi Build Labels

FiestaBoard's CI pipeline supports building ARM images on demand. When contributing:

- **Default builds**: `linux/amd64` only (~5 min)
- **With `pi` label on PR**: Adds `linux/arm/v7` and `linux/arm64` (~15 min)

To request ARM builds, add the `pi` or `raspberry-pi` label to your pull request before merging.

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

## Next Steps

- [Production Deployment](/docs/deployment/production) - Production best practices
- [Docker Setup](/docs/setup/docker-setup) - Docker architecture details
