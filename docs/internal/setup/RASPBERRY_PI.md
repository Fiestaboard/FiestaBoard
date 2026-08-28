# FiestaPi: Raspberry Pi setup

The easiest way to run FiestaBoard is to flash a Raspberry Pi with our pre-built **FiestaPi** image. Boot the Pi, point your browser at `http://fiestapi.local:4420`, and you're done.

## What you need

- **Raspberry Pi 3B or newer** (Pi 4 / Pi 5 also great; Pi Zero 2 W works as a stretch goal but isn't CI-tested)
- A microSD card (8 GB minimum, 16 GB+ recommended)
- A 5 V power supply for the Pi
- A wired Ethernet or Wi-Fi connection
- Your Vestaboard or split-flap display, on the same network as the Pi

## 1. Download the image

Grab the latest `FiestaPi-<version>-arm64.img.xz` from the [GitHub Releases](https://github.com/Fiestaboard/FiestaBoard/releases) page. The image is published by the `build-fiestapi.yml` workflow after each app release and typically lands ~45–60 minutes after the release shows up; the release page shows a "Raspberry Pi image is building" banner until it's attached.

## 2. Flash the SD card

The simplest tool is [Raspberry Pi Imager](https://www.raspberrypi.com/software/) — use **version 1.8.5 or newer** so OS customisation works with custom images:

1. Open Imager.
2. Choose device → your Pi model.
3. Choose OS → **Use custom** → select the `.img.xz` you downloaded.
4. Choose storage → your SD card.
5. Click **Next**. When the **"Would you like to apply OS customisation settings?"** dialog appears, click **Edit Settings** to pre-configure:
   - **Wi-Fi**: SSID, password, and **Wireless LAN country** (e.g. `US`, `GB`) — the country code is required, otherwise the Pi's Wi-Fi radio stays rfkill-blocked on first boot.
   - **Locale**: timezone and keyboard layout.
6. Click **Save**, then **Yes** to apply OS customisation, then **Yes** to confirm and write.

> **Note:** The **Customisation** entry in Imager's left-hand sidebar isn't a clickable step — it lights up briefly during the write. The customisation dialog is the pop-up that appears *after* you click **Next**. If no pop-up appears, you're on Imager < 1.8.5; upgrade and re-flash, or use the `fiestapi-wifi.txt` method below.

Other tools that work: [Balena Etcher](https://etcher.balena.io/), or `dd` on Linux/macOS:

```bash
xz -d FiestaPi-<version>-arm64.img.xz
sudo dd if=FiestaPi-<version>-arm64.img of=/dev/<your-sd-card> bs=4M status=progress
```

### Adding Wi-Fi credentials after flashing

If you flashed with `dd` or Balena Etcher (no Imager customisation), you can still configure Wi-Fi headlessly by dropping a plain-text file onto the SD card's boot partition before the first boot. The boot partition is the small FAT32 partition — it shows up as a drive called **`bootfs`** on Windows and macOS without any special tools.

1. Open the `bootfs` drive that appeared when you plugged in the SD card.
2. Create a file named **`fiestapi-wifi.txt`** with the following content:

   ```ini
   SSID=YourNetworkName
   PASSWORD=YourPassword
   COUNTRY=US
   ```

3. Save the file, eject the SD card, and insert it into the Pi.

On first boot FiestaPi sets the Wi-Fi regulatory country, connects to Wi-Fi, and **immediately deletes the file** so your credentials don't sit on the readable FAT partition.

- `COUNTRY=` is the [ISO-3166 alpha-2 country code](https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes) (e.g. `US`, `GB`, `DE`). It is **optional and defaults to `US`**, but is needed because Raspberry Pi OS keeps the Wi-Fi radio rfkill-blocked until a wireless regulatory country is set. Set it to your actual country if you're not in the US.
- For open (password-free) networks, omit the `PASSWORD` line.

> **Tip:** This works alongside Raspberry Pi Imager — if you used the customisation dialog, there's no need for this file.

## 3. First boot

1. Insert the SD card into your Pi.
2. Power it on.
3. Wait **2–3 minutes** for first boot (the Pi expands its filesystem and pulls Docker images on first start).
4. Open **http://fiestapi.local:4420** in any browser on the same network.

If `.local` doesn't resolve (some Windows networks), find the Pi's IP from your router and use that instead.

## 4. Run the welcome wizard

The browser will land on the FiestaBoard setup wizard. Pick your board, enter the API key, and pick a starting plugin or two. That's it.

## Optional: show a FiestaPanel on the Pi's HDMI port

The Pi can drive a TV or monitor directly — it boots into a minimal kiosk
browser showing the reserved `/p/display` FiestaPanel URL.

1. After flashing (or any time later), put an **empty file named
   `fiestapi-hdmi.txt`** on the boot partition — the same partition where
   `fiestapi-wifi.txt` goes.
2. Connect a screen over HDMI and boot.
3. In **Settings → Hardware → FiestaPanel**, create a panel (pick the
   screen's size) and turn on **Display output** for it. The screen follows
   whichever panel holds that role — exactly one at a time — so you can
   re-point it from the app without touching the Pi.

Until a panel is designated, the screen shows an instruction card. To turn
the kiosk off, delete `fiestapi-hdmi.txt` from the boot partition and
reboot — the browser then never starts and its memory is reclaimed (worth
doing on a Pi 3B you aren't using for HDMI output).

### Already have a FiestaPi flashed?

FiestaBoard's in-app updater only updates the app itself, not the Pi's
operating system — so Pis flashed before the kiosk existed don't have the
browser installed. One command over SSH retrofits it (and enables it):

```bash
curl -fsSL https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/scripts/fiestapi-hdmi-setup.sh | sudo bash
```

It installs the same pieces new images ship with, so everything above
applies afterwards. Disable later with
`sudo /opt/fiestaboard/fiestapi-hdmi-setup.sh --disable`.

## Updating

Updates are one click. When a new version is released, a banner appears in **Settings → System** with an **Update Now** button. Press it; the Pi pulls the new image and restarts FiestaBoard automatically. The page reloads when it's back. No SSH required.

If you'd rather update from the command line:

```bash
ssh fiesta@fiestapi.local
cd /opt/fiestaboard
docker compose pull && docker compose up -d
```

FiestaPi ships with two variables in `/opt/fiestaboard/.env` that together wire up **Update Now** end-to-end:

- `COMPOSE_PROFILES=fiestaupdater` — starts the updater sidecar, which is the process that actually runs `docker compose pull && docker compose up -d` against your compose file.
- `FIESTABOARD_PROFILE=pi` — tells the app it is running on a Pi, which flips the in-app **Auto-update** toggle to ON by default.

A unique `FIESTAUPDATER_TOKEN` is generated on first boot, so no extra configuration is needed.

## Troubleshooting

**Browser can't reach `fiestapi.local`** — Check that mDNS/Bonjour is enabled on your network. iOS, macOS, and most Linux distros ship with it. On Windows you may need [Bonjour Print Services](https://support.apple.com/kb/DL999). As a fallback, use the Pi's IP directly.

**"Connection is not secure" or an SSL error** — Use `http://`, not `https://`. FiestaPi serves the UI over plain HTTP on your local network and has no SSL certificate, so `https://fiestapi.local:4420` fails with `ERR_SSL_PROTOCOL_ERROR` or a warning page. Retype the address as **http://fiestapi.local:4420**. If your browser keeps forcing HTTPS, turn off its "Always use secure connections" / "HTTPS-Only Mode" setting for this site.

**SSH login** — Default user is `fiesta`, default password is `fiestaboard`. Change it on first login: `passwd`.

**Logs** — `ssh fiesta@fiestapi.local` then `docker logs -f fiestaboard`.

**Auto-update toggle** — In Settings → System, the Pi defaults this to ON. Turn it off if you'd rather click manually each time.

**I have a Pi Zero 2 W** — It might work, but it's tight on RAM. Disable plugins you don't use to keep memory pressure down.
