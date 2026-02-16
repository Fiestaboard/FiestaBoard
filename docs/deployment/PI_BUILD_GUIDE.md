# Raspberry Pi Build Guide

## Overview

Raspberry Pi Docker images are built **on-demand** to save CI time. By default, releases only build for `linux/amd64` (x86-64 systems).

## How to Enable Pi Builds

### Option 1: Add Label Before Merging
1. Open your PR on GitHub
2. Add the `pi` or `raspberry-pi` label
3. Merge the PR to `main`
4. The release workflow will automatically build multi-architecture images

### Option 2: Add Label to Existing PR
1. Find a recently merged PR (within the last minute)
2. Add the `pi` label
3. The next merge will trigger Pi builds

## What Gets Built

### Default (No `pi` label)
- **Platform:** `linux/amd64` only
- **Build time:** ~5 minutes
- **Best for:** Regular releases, x86-64 systems

### With `pi` Label
- **Platforms:** `linux/amd64`, `linux/arm/v7`, `linux/arm64`
- **Build time:** ~15 minutes
- **Best for:** Releases that need Raspberry Pi support
- **Compatible with:**
  - Raspberry Pi 3B+ (arm/v7)
  - Raspberry Pi Zero 2W (arm/v7)
  - Raspberry Pi 4 (arm64)
  - Raspberry Pi 5 (arm64)

## Release Notes

When Pi builds are included, release notes will show:

```markdown
## Docker Images

**Platforms:** `linux/amd64`, `linux/arm/v7`, `linux/arm64` 🍓

### 🍓 Raspberry Pi Support

This release includes multi-architecture images that work on Raspberry Pi (arm/v7 and arm64).
Simply use the same `docker pull` commands above on your Pi!
```

## Testing Pi Builds

After merging a PR with the `pi` label:

1. Check the release workflow runs successfully (~15 min)
2. Verify images on GHCR show all architectures
3. Test pulling and running on a Raspberry Pi:

```bash
# On your Raspberry Pi
docker pull ghcr.io/fiestaboard/fiestaboard:latest
docker-compose up -f docker-compose.ghcr.yml up -d
```

## Technical Details

### Build Tools Required

The `Dockerfile.api` includes build tools for ARM:
- `gcc` - GNU C compiler
- `g++` - GNU C++ compiler
- `make` - Build automation

These are needed to compile Python packages with C extensions:
- `httptools` (dependency of `uvicorn`)
- `uvloop` (dependency of `uvicorn[standard]`)

### Conditional Build Logic

The workflow checks for the `pi` label on the merged PR:

```yaml
platforms: ${{ steps.bump_type.outputs.build_pi == 'true' && 'linux/amd64,linux/arm/v7,linux/arm64' || 'linux/amd64' }}
```

## Troubleshooting

### Build Fails on ARM
- Ensure `Dockerfile.api` has build tools installed
- Check that Python packages support ARM architecture
- Review workflow logs for specific compilation errors

### Wrong Platform Built
- Verify the PR had the `pi` label **before** merging
- Label must be added within 60 seconds of merge for detection
- Check release notes to confirm which platforms were built

## CI Time Savings

| Build Type | Platforms | Time | Savings |
|------------|-----------|------|---------|
| Default    | amd64     | ~5m  | Baseline |
| With Pi    | amd64, arm/v7, arm64 | ~15m | -10m per release |

By making Pi builds opt-in, we save ~10 minutes on most releases while still supporting Pi when needed.

