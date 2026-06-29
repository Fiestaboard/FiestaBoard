# FiestaPi

A flashable Raspberry Pi OS image with FiestaBoard pre-installed and self-updating out of the box.

**Minimum supported hardware:** Raspberry Pi 3B (1 GB RAM, 64-bit). Pi 4 / Pi 5 work great. Pi Zero 2 W is a stretch goal (best-effort, no CI).

## What's in the image

- Raspberry Pi OS Lite (64-bit, Trixie)
- **Kernel pinned to the 6.12 LTS series.** Trixie's default 6.18.x kernel regressed the
  lan78xx driver and breaks wired ethernet on the Pi 3B+ ([raspberrypi/linux#7436](https://github.com/raspberrypi/linux/issues/7436)).
  FiestaPi holds the last-known-good `6.12.75` until that's fixed upstream — see
  `stage-fiestaboard/00-pin-kernel/`. Remove that stage (and the apt pin it writes) once
  #7436 is resolved.
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

**Pre-publish verification gate.** Because the image is built from a moving Trixie base
(`apt` pulls live packages on every build), an upstream regression can ride into the image
silently — it has before (the raspi-firmware [#2034](https://github.com/raspberrypi/firmware/issues/2034)
Pi-3 boot brick, the 6.18.x [#7436](https://github.com/raspberrypi/linux/issues/7436) Pi 3B+
ethernet break). The workflow now loop-mounts the freshly built `.img` and **fails before any
release attach** if it ships a known-bad kernel/firmware version or is missing the Pi-3 boot
files (`start.elf`, `kernel8.img`, `bcm2710-rpi-3-b.dtb`). The debug artifact is still uploaded
on failure; only the *published* release is gated. Update the denylist alongside
`stage-fiestaboard/00-pin-kernel/` as upstream issues open and close.

## Layout

```
pi-image/
├── README.md              ← this file
├── config                 ← pi-gen top-level config (image name, user, locale)
├── firstboot.sh           ← runs once on first boot
└── stage-fiestaboard/     ← custom pi-gen stage
    ├── prerun.sh
    ├── EXPORT_IMAGE       ← marks this stage as the one to export
    ├── 00-pin-kernel/
    │   └── 00-run.sh      ← pins kernel to 6.12 LTS (linux#7436 workaround)
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
