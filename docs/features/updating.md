---
sidebar_position: 10
description: "FiestaBoard 5.0 introduces one-click in-app updates. Learn how Update Now works, how to opt in on Docker installs, and how auto-update works on FiestaPi."
keywords: [FiestaBoard update, in-app update, self-update, Update Now, fiestaupdater, FiestaPi update]
---

# In-App Updates

Starting in FiestaBoard **5.0**, you can update FiestaBoard directly from the web UI — no terminal required.

## The Update Now button

When a new version is available, a banner appears in **Settings → System**. Click **Update Now**, confirm, and FiestaBoard handles the rest:

1. The `fiestaupdater` sidecar pulls the new Docker image in the background
2. FiestaBoard restarts with the new image
3. A full-screen overlay polls the API every 2 seconds
4. When the new version is detected, the page reloads automatically

The whole process takes about a minute on a fast connection, a bit longer on a Raspberry Pi.

## Update check interval

In **Settings → System**, there's a **Check for updates** dropdown that
controls how often FiestaBoard looks for a new release in the background:

| Option | Default for | Notes |
|---|---|---|
| **Every day** | FiestaPi | Same cadence as before; you'll hear about updates the day they ship. |
| **Every week** | Docker / manual | New default. Stay current without daily noise. |
| **Every month** | — | Quiet option that still nudges you periodically. |
| **Manual only** | — | No background checks; click the refresh button on the System card to check on demand. |

When a check finds a newer version, the "Update Available" banner appears
on Settings → System. Picking the matching cadence for your install means
you don't have to remember to open Settings to discover an update.

You can change it any time; the running scheduler picks up the new value
within an hour without needing a restart.

## How it works (technical)

FiestaBoard uses a small companion container called `fiestaupdater`. It sits on the same Docker Compose internal network as FiestaBoard and has access to the Docker socket — FiestaBoard itself does not.

When you click Update Now, the web UI POSTs to the FiestaBoard API, which calls the updater over the internal network. The updater runs `docker compose pull && docker compose up -d` against your compose file. Because it's a separate process, FiestaBoard can update itself without getting cut off mid-response.

**See also:** [FiestaUpdater reference](/docs/deployment/fiestaupdater) for the full sidecar architecture, HTTP API, and security model.

## Opting in on Docker installs

The updater is opt-in for Docker and manual installs (it's already on for FiestaPi).

**Via the install script (easiest):** Run `./scripts/install.sh` (or `install.ps1` on Windows) — it asks about this and configures everything.

**Manually:** Edit your `.env` file:

```bash
COMPOSE_PROFILES=fiestaupdater
FIESTAUPDATER_TOKEN=<64-hex-char random string>
```

Generate a token:

```bash
head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
```

Then restart:

```bash
docker compose up -d
```

The Update Now button will appear in Settings → System once the sidecar is healthy.

## Security

- The updater is only reachable on the Docker Compose internal network — it's never published on a host port
- All requests require a bearer token (`FIESTAUPDATER_TOKEN`), unique to your install
- The sidecar can only restart the service listed in `FIESTAUPDATER_SERVICE` — no arbitrary container access

If you prefer not to use the Docker socket at all, leave the `fiestaupdater` profile off and update manually instead.

## Updating manually (always works)

The Update Now button is a convenience shortcut. You can always update from the terminal:

```bash
# For Docker Hub installs — cd to the SAME folder you originally ran
# `docker compose up -d` from. That's where your ./data folder lives.
cd ~/fiestaboard
docker compose -f docker-compose.hub.yml pull
docker compose -f docker-compose.hub.yml up -d

# For FiestaPi (SSH in first)
ssh fiesta@fiestapi.local
cd /opt/fiestaboard
docker compose pull && docker compose up -d
```

:::caution Always `cd` first on Docker installs
The compose file uses a relative bind mount (`./data:/app/data`), so persistence depends on your current shell directory. If you run `docker compose pull && up -d` from a different folder than your original install, FiestaBoard will come up with empty settings — your data isn't deleted, but Docker is mounting a different (empty) folder. See [Troubleshooting → Settings or board credentials are gone after an update](/docs/troubleshooting#settings-or-board-credentials-are-gone-after-an-update) if this has happened.
:::

## The beta channel

Beta builds come from the `next` branch and carry changes that have not reached
a stable release yet. They are published on every merge, so a beta is newer than
stable but has had far less time in front of real boards.

:::caution Betas can break, and going back is not free
A beta may migrate your settings and pages to a format stable does not
understand. FiestaBoard refuses to read such a file rather than misinterpret it,
so returning to stable means restoring a backup. **Take one before you opt in:**
Settings → System → Backup → Export.
:::

### FiestaPi

Settings → System → **Release channel** → **Join the beta**.

A backup is taken automatically before the switch, and FiestaBoard restarts onto
the beta build. From then on **Update Now** keeps you on betas — it moves you
from one beta to the next, not back to stable.

Joining is one-way on a Pi for now; see [Going back to stable](#going-back-to-stable)
before you opt in.

The choice survives a reboot. A Pi re-pulls its images on every boot, which would
otherwise put you back on stable, so FiestaBoard re-applies your channel at
startup if the build that came up does not match it.

### Docker installs

You already control which build you run — it is the image tag in your compose
file. Edit `docker-compose.hub.yml`:

```yaml
services:
  fiestaboard:
    image: fiestaboard/fiestaboard:beta # was :latest
```

Then, from the folder you originally installed in:

```bash
cd ~/fiestaboard
docker compose -f docker-compose.hub.yml pull
docker compose -f docker-compose.hub.yml up -d
```

Two tags are published:

| Tag | Use it when |
| --- | --- |
| `beta` | You want the newest beta, and want Update Now to keep you on betas |
| `9.0.0-beta.12` | You want to stay on one exact build, or you are filing a bug |

The in-app **Update Now** button pulls whatever tag your compose file names, so
once you are on `:beta` it keeps you on betas. Nothing else to configure.

### Home Assistant

Not available. The HA Supervisor owns updating for add-ons — FiestaBoard cannot
change the image it runs, and the Release channel card will tell you so rather
than offering a button that cannot work. Supporting betas there means shipping a
separate add-on entry, which is not planned yet.

### Going back to stable

**Docker** — set the tag back to `:latest`, pull, bring the stack up again, then
restore the backup you took before opting in.

If you skipped that backup and the app reports a schema it cannot read, your data
is still on disk and intact. The newer FiestaBoard can still read it, so going
back to `:beta` gets you running again — export a backup, then switch.

**FiestaPi** — there is no in-app way back yet.

:::warning A FiestaPi cannot leave the beta from the app
Joining is currently one-way on a Pi. The control to return to stable has not
shipped, so treat joining as a decision to stay on beta for now. If that is not
what you want, wait — it is being worked on.
:::

## Troubleshooting

**The Update Now button isn't showing** — Check the status panel just below the button area in Settings → System. It will say whether the updater sidecar is reachable. Most common cause: `COMPOSE_PROFILES=fiestaupdater` isn't set in `.env`, or the sidecar container isn't running.

**Update started but the page never came back** — Open `http://fiestaboard.local:4420` (or `localhost:4420`) again after a minute. If it's still down, check logs: `docker logs fiestaboard`. As a last resort, `docker compose up -d` will bring you back online.

**I joined the beta but came back on stable** — The switch works by pointing
the image name in your compose file at the beta build, and an out-of-date
updater sidecar can undo that when it recreates the container. FiestaBoard re-applies your channel at
startup, so the box usually arrives on the beta a minute later after an extra
restart. To stop it happening: reboot a FiestaPi to pick up the current sidecar,
or on Docker run `docker compose pull fiestaupdater && docker compose up -d`.

**I want to roll back** — Pin the previous image tag in `docker-compose.yml`, then `docker compose up -d`. Automated rollback is planned for a future release.
