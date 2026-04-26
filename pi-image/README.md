# FiestaPi

A flashable Raspberry Pi OS image with FiestaBoard pre-installed and self-updating out of the box.

**Minimum supported hardware:** Raspberry Pi 3B (1 GB RAM, 64-bit). Pi 4 / Pi 5 work great. Pi Zero 2 W is a stretch goal (best-effort, no CI).

## What's in the image

- Raspberry Pi OS Lite (64-bit, latest stable release)
- Docker + Docker Compose (apt + convenience repo)
- FiestaBoard, pre-pulled and configured to start on boot
- `fiestaupdater` sidecar enabled by default — Settings → Update Now works immediately
- 1 GB swap file
- mDNS hostname `fiestapi.local`
- `FIESTABOARD_PROFILE=pi` env baked in (flips the in-app auto-update toggle to default ON)
- First-boot script that generates a unique `FIESTAUPDATER_TOKEN`
- Post-flash Wi-Fi provisioning: drop `fiestapi-wifi.txt` on the boot partition — see [RASPBERRY_PI.md](../docs/setup/RASPBERRY_PI.md)

## Building locally

You need [pi-gen](https://github.com/RPi-Distro/pi-gen). On Linux:

```bash
git clone --depth=1 https://github.com/RPi-Distro/pi-gen.git
cd pi-gen
# Symlink our stage in.
ln -s ../../FiestaBoard/pi-image/stage-fiestaboard ./stage-fiestaboard
cp ../../FiestaBoard/pi-image/config ./config
sudo ./build-docker.sh
```

The output `.img.xz` lands in `pi-gen/deploy/`.

## CI

Builds nightly and on every `v5.*` git tag. See `.github/workflows/build-fiestapi.yml`. Output is uploaded to GitHub Releases as `fiestapi-<version>-arm64.img.xz`.

## Layout

```
pi-image/
├── README.md              ← this file
├── config                 ← pi-gen top-level config (image name, user, locale)
├── firstboot.sh           ← runs once on first boot
└── stage-fiestaboard/     ← custom pi-gen stage
    ├── prerun.sh
    ├── 00-install-docker/
    │   └── 00-run-chroot.sh
    └── 01-install-fiestaboard/
        ├── files/
        │   ├── docker-compose.yml
        │   ├── env.template
        │   └── fiestaboard.service
        └── 00-run-chroot.sh
```
