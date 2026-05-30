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
- `FIESTABOARD_PROFILE=pi` env baked in (flips the in-app auto-update toggle to default ON, and seeds the instance name to "FiestaPi" on first boot)
- First-boot script that generates a unique `FIESTAUPDATER_TOKEN`
- Post-flash Wi-Fi provisioning: drop `fiestapi-wifi.txt` (with `SSID=`, `PASSWORD=`, optional `COUNTRY=`) on the boot partition — see [RASPBERRY_PI.md](../docs/setup/RASPBERRY_PI.md). The first-boot script sets the wireless regulatory country and unblocks rfkill before connecting, so Wi-Fi works even on a fresh image.

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

Built by `.github/workflows/build-fiestapi.yml` on three triggers:

- **Major-version tags** (`v5.0.0`, `v6.0.0`, …) — attached to the GitHub Release.
- **Weekly schedule** (Tuesdays 06:00 UTC) — keeps base packages fresh between releases.
- **Manual dispatch** — Actions tab → *Build FiestaPi image* → *Run workflow*, or:

  ```bash
  gh workflow run build-fiestapi.yml --ref main
  gh run watch
  ```

Output is uploaded as a workflow artifact (`FiestaPi-<version>-arm64`) and, for tag builds, attached to the GitHub Release as `FiestaPi-<version>-arm64.img.xz`.

## Layout

```
pi-image/
├── README.md              ← this file
├── config                 ← pi-gen top-level config (image name, user, locale)
├── firstboot.sh           ← runs once on first boot
└── stage-fiestaboard/     ← custom pi-gen stage
    ├── prerun.sh
    ├── EXPORT_IMAGE       ← marks this stage as the one to export
    └── 01-install-fiestaboard/
        ├── 00-packages    ← apt packages installed in the chroot
        ├── 00-run.sh      ← installs docker-ce + FiestaBoard in chroot
        └── files/
            ├── docker-compose.yml
            ├── env.template
            ├── fiestaboard.service
            ├── fiestapi-heal-mdns.service
            ├── fiestapi-heal-mdns.timer
            ├── firstboot.sh
            └── heal-mdns.sh
```
