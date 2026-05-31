---
sidebar_position: 1
description: "Run FiestaBoard on a Raspberry Pi. Flash the FiestaPi image for zero-config setup, or use a Pi you already have with Docker."
keywords: [FiestaBoard Raspberry Pi, FiestaPi, Pi deployment, Raspberry Pi 4, Pi Zero 2W, self-hosted, split-flap Pi]
---

# Raspberry Pi

Run FiestaBoard on a Raspberry Pi for a dedicated, always-on dashboard controller.

## Recommended: Flash the FiestaPi image

The fastest path is the **FiestaPi** pre-built image. Flash a microSD card, boot, open a browser — FiestaBoard is running and self-updating out of the box. No Docker setup, no command line.

**→ [FiestaPi Quick Start](/docs/setup/raspberry-pi)**

---

## Advanced: Install on an existing Pi with Docker

Already have a Raspberry Pi running with Docker? You can run FiestaBoard the same way as any Docker install.

### Compatible models

| Model | Architecture | Status |
|-------|-------------|--------|
| Raspberry Pi 3B+ | `linux/arm64` | Supported (64-bit OS required) |
| Raspberry Pi Zero 2 W | `linux/arm64` | Supported (64-bit OS required) |
| Raspberry Pi 4 | `linux/arm64` | Supported |
| Raspberry Pi 5 | `linux/arm64` | Supported |

> **Note:** 32-bit ARM (`linux/arm/v7`) is not supported. Node.js dropped ARM32v7 in v20+. Use 64-bit Raspberry Pi OS (Bookworm or later).

### Install Docker (if needed)

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
# Log out and back in, then verify:
docker --version
```

### Start FiestaBoard

Using pre-built images from Docker Hub (recommended — no build step):

```bash
docker compose -f docker-compose.hub.yml up -d
```

Open **http://localhost:4420** in a browser on the same network.

### Enable in-app updates

Add these lines to your `.env` to enable the one-click Update Now button:

```bash
COMPOSE_PROFILES=fiestaupdater
FIESTAUPDATER_TOKEN=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
```

Then restart: `docker compose -f docker-compose.hub.yml up -d`. See [In-App Updates](/docs/features/updating) for more detail, or the [FiestaUpdater reference](/docs/deployment/fiestaupdater) for the full sidecar configuration.

### Auto-start on boot

Create a systemd unit so FiestaBoard starts automatically:

```bash
sudo tee /etc/systemd/system/fiestaboard.service > /dev/null << 'EOF'
[Unit]
Description=FiestaBoard
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/pi/FiestaBoard
ExecStart=/usr/bin/docker compose -f docker-compose.hub.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.hub.yml down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable fiestaboard
sudo systemctl start fiestaboard
```

### Performance tips

- **Use a fast SD card** — Class 10 or higher, ideally A2-rated
- **Consider USB boot** — Booting from a USB SSD significantly improves performance
- **Add a heatsink** — Sustained Docker workloads can throttle an uncooled Pi 3B
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
