# FiestaPi: Raspberry Pi setup

The easiest way to run FiestaBoard is to flash a Raspberry Pi with our pre-built **FiestaPi** image. Boot the Pi, point your browser at `http://fiestapi.local:4420`, and you're done.

## What you need

- **Raspberry Pi 3B or newer** (Pi 4 / Pi 5 also great; Pi Zero 2 W works as a stretch goal but isn't CI-tested)
- A microSD card (8 GB minimum, 16 GB+ recommended)
- A 5 V power supply for the Pi
- A wired Ethernet or Wi-Fi connection
- Your Vestaboard or split-flap display, on the same network as the Pi

## 1. Download the image

Grab the latest `fiestapi-<version>-arm64.img.xz` from the [GitHub Releases](https://github.com/Fiestaboard/FiestaBoard/releases) page.

## 2. Flash the SD card

The simplest tool is [Raspberry Pi Imager](https://www.raspberrypi.com/software/):

1. Open Imager.
2. Choose device → your Pi model.
3. Choose OS → **Use custom** → select the `.img.xz` you downloaded.
4. Choose storage → your SD card.
5. (Optional) Click the gear icon to pre-configure Wi-Fi credentials and your timezone.
6. Click Write.

Other tools that work: [Balena Etcher](https://etcher.balena.io/), or `dd` on Linux/macOS:

```bash
xz -d fiestapi-<version>-arm64.img.xz
sudo dd if=fiestapi-<version>-arm64.img of=/dev/<your-sd-card> bs=4M status=progress
```

## 3. First boot

1. Insert the SD card into your Pi.
2. Power it on.
3. Wait about a minute (longer on the very first boot — it expands the filesystem and pulls Docker images).
4. Open **http://fiestapi.local:4420** in any browser on the same network.

If `.local` doesn't resolve (some Windows networks), find the Pi's IP from your router and use that instead.

## 4. Run the welcome wizard

The browser will land on the FiestaBoard setup wizard. Pick your board, enter the API key, and pick a starting plugin or two. That's it.

## Updating

Updates are one click. When a new version is released, a banner appears in **Settings → System** with an **Update Now** button. Press it; the Pi pulls the new image and restarts FiestaBoard automatically. The page reloads when it's back. No SSH required.

If you'd rather update from the command line:

```bash
ssh fiesta@fiestapi.local
cd /opt/fiestaboard
docker compose pull && docker compose up -d
```

## Troubleshooting

**Browser can't reach `fiestapi.local`** — Check that mDNS/Bonjour is enabled on your network. iOS, macOS, and most Linux distros ship with it. On Windows you may need [Bonjour Print Services](https://support.apple.com/kb/DL999). As a fallback, use the Pi's IP directly.

**SSH login** — Default user is `fiesta`, default password is `fiestaboard`. Change it on first login: `passwd`.

**Logs** — `ssh fiesta@fiestapi.local` then `docker logs -f fiestaboard`.

**Auto-update toggle** — In Settings → System, the Pi defaults this to ON. Turn it off if you'd rather click manually each time.

**I have a Pi Zero 2 W** — It might work, but it's tight on RAM. Disable plugins you don't use to keep memory pressure down.
