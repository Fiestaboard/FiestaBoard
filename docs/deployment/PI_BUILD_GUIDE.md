# Raspberry Pi Build Guide

## Quick Start - Running FiestaBoard on a Raspberry Pi

The easiest way to run FiestaBoard on a Raspberry Pi is to pull the pre-built Docker image from Docker Hub. No need to clone the repo or build anything.

### Prerequisites

- **Raspberry Pi 3B+, Zero 2W, 4, or 5** with a recent Raspberry Pi OS
- **Docker** installed on your Pi ([install guide](https://docs.docker.com/engine/install/debian/))

> **Tip:** On Raspberry Pi OS, you can install Docker with:
> ```bash
> curl -fsSL https://get.docker.com | sh
> sudo usermod -aG docker $USER
> # Log out and back in for the group change to take effect
> ```

### Setup

```bash
# Create a project folder
mkdir ~/FiestaBoard && cd ~/FiestaBoard

# Pull the pre-built image from Docker Hub (docker compose up also does this automatically)
docker pull fiestaboard/fiestaboard:latest
```

Next, create a `docker-compose.yml` file in `~/FiestaBoard/`:

```yaml
services:
  fiestaboard:
    image: fiestaboard/fiestaboard:latest
    container_name: fiestaboard
    env_file: .env
    environment:
      - PRODUCTION=true
    restart: unless-stopped
    pull_policy: always
    ports:
      - "4420:3000"
    volumes:
      - ./data:/app/data
```

Then create a `.env` file with your board API key:

```bash
nano .env
# Add your BOARD_API_MODE, API key, and BOARD_HOST (see env.example for all options)
```

Start FiestaBoard:

```bash
docker compose up -d
```

Once running, open **http://\<your-pi-ip\>:4420** in a browser on any device on your network.

### Updating

```bash
cd ~/FiestaBoard
docker compose pull
docker compose up -d
```

---

## How Pi Builds Work (for Contributors)

### Overview

Every release automatically builds multi-architecture Docker images for `linux/amd64`, `linux/arm/v7`, and `linux/arm64`. This means every release supports Raspberry Pi out of the box.

## What Gets Built

- **Platforms:** `linux/amd64`, `linux/arm/v7`, `linux/arm64`
- **Build time:** ~15 minutes
- **Compatible with:**
  - Raspberry Pi 3B+ (arm/v7)
  - Raspberry Pi Zero 2W (arm/v7)
  - Raspberry Pi 4 (arm64)
  - Raspberry Pi 5 (arm64)
  - Any x86-64 system (amd64)

## Release Notes

Release notes will show:

```markdown
## Docker Images

**Platforms:** `linux/amd64`, `linux/arm/v7`, `linux/arm64`

### Raspberry Pi Support

This release includes multi-architecture images that work on Raspberry Pi (arm/v7 and arm64).
Simply use the same `docker pull` commands above on your Pi!
```

## Testing Pi Builds

After a release:

1. Check the release workflow runs successfully (~15 min)
2. Verify images on Docker Hub show all architectures
3. Test pulling and running on a Raspberry Pi:

```bash
# On your Raspberry Pi
docker pull fiestaboard/fiestaboard:latest
docker-compose -f docker-compose.hub.yml up -d
```

## Technical Details

### Build Tools Required

The `Dockerfile` includes build tools for ARM:
- `gcc` - GNU C compiler
- `g++` - GNU C++ compiler
- `make` - Build automation

These are needed to compile Python packages with C extensions:
- `httptools` (dependency of `uvicorn`)
- `uvloop` (dependency of `uvicorn[standard]`)

### Multi-Architecture Build

The workflow uses QEMU emulation and Docker Buildx to build for all platforms:

```yaml
platforms: linux/amd64,linux/arm/v7,linux/arm64
```

## Troubleshooting

### Build Fails on ARM
- Ensure `Dockerfile` has build tools installed
- Check that Python packages support ARM architecture
- Review workflow logs for specific compilation errors

