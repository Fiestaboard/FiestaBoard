---
sidebar_position: 0
description: "Flash a Raspberry Pi with FiestaPi and have FiestaBoard running in minutes — no Docker setup, no command line. Self-updating out of the box."
keywords: [FiestaPi, FiestaBoard Raspberry Pi, flash Raspberry Pi, Pi image, Raspberry Pi Imager, Vestaboard Pi setup]
---

# FiestaPi Quick Start

The easiest way to run FiestaBoard. Flash a microSD card, boot your Pi, open a browser — done.

**No Docker setup. No command line. Self-updating out of the box.**

:::info What's in the box
FiestaPi is a pre-built Raspberry Pi OS image with FiestaBoard, Docker, and the self-update sidecar all pre-installed and configured to start on boot. All you do is flash and go.
:::

## What You Need

- **Raspberry Pi 3B or newer** (Pi 4 / Pi 5 work great too)
- A **microSD card** — 8 GB minimum, 16 GB+ recommended
- A **5V power supply** for your Pi
- Your Pi on the **same network** as your Vestaboard or split-flap display
- Your **board's API key** ([where to find it](/docs/setup/quick-start#getting-your-board-api-key))

## Step 1 — Download the FiestaPi image

👉 **[Download the latest FiestaPi image](https://github.com/Fiestaboard/FiestaBoard/releases/latest)**

On the Releases page, grab the file named `FiestaPi-<version>-arm64.img.xz`.

:::tip Not sure which file to pick?
Download the `.img.xz` file. It's compressed — Raspberry Pi Imager handles decompression automatically.
:::

## Step 2 — Flash the microSD card

The simplest tool is [**Raspberry Pi Imager**](https://www.raspberrypi.com/software/) (free, works on Mac/Windows/Linux). Use **version 1.8.5 or newer** so OS customisation works with custom images.

1. Open Raspberry Pi Imager
2. Click **Choose Device** → select your Pi model
3. Click **Choose OS** → scroll to the bottom → **Use custom** → pick the `.img.xz` you downloaded
4. Click **Choose Storage** → select your microSD card
5. Click **Next**
6. When prompted **"Would you like to apply OS customisation settings?"**, click **Edit Settings** and pre-configure:
   - **Wi-Fi**: SSID, password, and **Wireless LAN country** (e.g. `US`, `GB`) — the country is required, otherwise the Pi's Wi-Fi radio stays disabled on first boot
   - **Locale**: timezone and keyboard layout
   - **General → Set username and password**: optional, replaces the default `fiesta` / `fiestaboard`
7. Click **Save**, then **Yes** to apply OS customisation, then **Yes** to confirm the write
8. Wait ~5 minutes for the flash to complete

:::warning "Customisation" step is greyed out?
The **Customisation** step in the Imager sidebar is only used during the flash — it's normal for it to look disabled in earlier steps. The customisation dialog appears as a pop-up *after* you click **Next** in step 5 above. If the pop-up doesn't appear at all, you're on a version of Imager older than 1.8.5; [upgrade Raspberry Pi Imager](https://www.raspberrypi.com/software/) and re-flash, or use the `fiestapi-wifi.txt` method below.
:::

Alternative tools: [Balena Etcher](https://etcher.balena.io/) works too. On Linux/macOS with `dd`:
```bash
xz -d FiestaPi-<version>-arm64.img.xz
sudo dd if=FiestaPi-<version>-arm64.img of=/dev/<your-sd-card> bs=4M status=progress
```

### Adding Wi-Fi credentials without Raspberry Pi Imager

If you flashed with Balena Etcher or `dd` and didn't set Wi-Fi credentials during flashing, you can still configure Wi-Fi headlessly — no keyboard or monitor needed.

After flashing, plug the SD card back into your computer. A small FAT32 drive called **`bootfs`** will appear (visible from any OS without special tools).

1. Create a file called **`fiestapi-wifi.txt`** in the root of the `bootfs` drive
2. Paste in your Wi-Fi details:

   ```
   SSID=YourNetworkName
   PASSWORD=YourPassword
   COUNTRY=US
   ```

3. Save the file and eject the SD card

On first boot FiestaPi sets the Wi-Fi regulatory country, connects to Wi-Fi, and **immediately deletes the file** so your credentials are never left sitting on the readable FAT partition.

- The `COUNTRY=` line is the [ISO-3166 alpha-2 country code](https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes) (e.g. `US`, `GB`, `DE`, `AU`). It is **optional and defaults to `US`**, but is needed because Raspberry Pi OS keeps the Wi-Fi radio disabled (rfkill-blocked) until a wireless regulatory country is set. Set it to your actual country if you're not in the US.
- For open (password-free) networks, omit the `PASSWORD` line entirely.

:::tip Already used Raspberry Pi Imager's OS customisation?
If you already entered Wi-Fi credentials and a Wireless LAN country via Imager's settings screen, the `fiestapi-wifi.txt` file isn't needed — Imager handles it for you.
:::

## Step 3 — Boot your Pi

1. Insert the microSD card into your Pi
2. Plug it in
3. Wait **2–3 minutes** — the first boot is longer than usual (it expands the filesystem and pulls Docker images)

That's it. FiestaBoard starts automatically.

## Step 4 — Open FiestaBoard

On any device on the same network, open:

**→ [Open FiestaBoard at fiestapi.local:4420](http://fiestapi.local:4420)**

You'll see the FiestaBoard setup wizard. Enter your board API key, choose your board type, and you're running.

:::tip Can't reach `fiestapi.local`?
`.local` addresses use mDNS. It works on Mac, iOS, Android, and most Linux systems out of the box. On **Windows**, you may need [Bonjour Print Services](https://support.apple.com/kb/DL999) if it's not already installed. As a fallback, find the Pi's IP address in your router's admin page and use that directly: `http://192.168.x.x:4420`.
:::

## Updating FiestaBoard

When a new version is released, a banner appears in **Settings → System** with an **Update Now** button. Tap it — FiestaBoard updates itself and the page reloads when it's done. No SSH, no terminal.

Auto-update is enabled by default on FiestaPi. See [In-App Updates](/docs/features/updating) for more detail.

## Default credentials

| Thing | Default |
|---|---|
| Hostname | `fiestapi.local` |
| Web UI port | `4420` |
| SSH user | `fiesta` |
| SSH password | `fiestaboard` |

:::warning Change your SSH password
On first SSH login, run `passwd` to set a strong password.
:::

## Troubleshooting

**Pi won't connect to Wi-Fi** — The most common cause is a missing wireless regulatory country (Raspberry Pi OS keeps the radio rfkill-blocked until one is set). If you flashed with Imager, re-flash and set **Wireless LAN country** in **Edit Settings**. Otherwise, drop a `fiestapi-wifi.txt` file on the `bootfs` partition with `SSID=`, `PASSWORD=`, and (recommended) a `COUNTRY=` line — see [Adding Wi-Fi credentials without Raspberry Pi Imager](#adding-wi-fi-credentials-without-raspberry-pi-imager) above. Or plug in an Ethernet cable, SSH in, and run `sudo raspi-config` → **Localisation Options** → **WLAN Country** to fix it manually.

**FiestaBoard isn't starting** — SSH in (`ssh fiesta@fiestapi.local`) and check logs: `docker logs fiestaboard`. If Docker images haven't pulled yet, wait another minute.

**I want to SSH in** — `ssh fiesta@fiestapi.local` (default password `fiestaboard` — change it!).

**Can I run this on a Pi Zero 2 W?** — Yes, but it's tight on RAM. Disable unused plugins to reduce memory pressure.

**Where's my data if I re-flash?** — FiestaBoard data lives in `/opt/fiestaboard/data/`. Back it up with `scp -r fiesta@fiestapi.local:/opt/fiestaboard/data/ ./backup` before re-flashing.
