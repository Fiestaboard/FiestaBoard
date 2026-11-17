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

When you click Update Now, the web UI POSTs to the FiestaBoard API, which calls the updater over the internal network. Stable updates normally ask the updater to pull and recreate the Compose service. Preview-channel updates use the updater’s install endpoint with a selected channel/version image; they do not simply pull the tag written in the Compose file. Because it's a separate process, FiestaBoard can update itself without getting cut off mid-response.

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

## Updating manually {#updating-manually-always-works}

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

## Stable, Beta and Alpha {#the-beta-channel}

See [Release Channels](/docs/features/release-channels) for the published versions,
image tags and controls available in each release. The branch named `alpha`
publishes Beta; `v11` publishes the separate Alpha preview. Builds are published
by reviewed version releases, not on every feature merge.

At the November 17, 2026 checkpoint, Stable 10.3.3 and Beta 10.3.4-beta.0 offer
Stable/Beta controls but **no Alpha choice**. Joining the currently published
Beta does not add the Alpha chooser. Published v11 Alpha includes the three-choice
chooser; the 10.x backport remains an unpublished candidate.

### FiestaPi and Docker

In-app channel changes require a reachable FiestaUpdater sidecar. Export a backup
before joining a preview. A move to a newer major through the chooser requires
explicit confirmation and a successful automatic backup. Returning to an older
channel can restore the join snapshot and lose changes made since then; it also
signs out sessions. Return controls exist in the published source, but the v11
production-image upgrade/restore gate is still incomplete.

For a manual preview installation, use the [v11 guide](/docs/setup/v11-preview).
To upgrade an existing installation, follow the [backup and image-swap
procedure](/docs/setup/v11-upgrade). Keep the original install directory and
mounts. On startup the hub can reapply a saved channel choice, so verify the
version after a restart as well as after the initial switch.

### Home Assistant

The HA Supervisor owns add-on updates. FiestaBoard cannot switch its managed
image through the in-app channel control. These instructions do not provide a
Beta or Alpha add-on.

### Going back to stable

Read [Recovery options](/docs/setup/v11-upgrade#recovery-options) **before**
changing the image. Managed return restores its available join snapshot before
requesting the destination channel image. It does not promise to restore every
file or installed plugin version, and a missing snapshot can leave restoration
undone.

Manual recovery needs a known-good image **and compatible pre-upgrade data**.
Sign out everywhere before stopping for a downgrade, restore the compatible
baseline before starting the older image, and verify the result. Exporting from
a newer build does not convert its schemas for an older release. Do not start an older image on
newer data and assume an apparently empty UI means the data was deleted.

## Troubleshooting

**The Update Now button isn't showing** — Check the status panel just below the button area in Settings → System. It will say whether the updater sidecar is reachable. Most common cause: `COMPOSE_PROFILES=fiestaupdater` isn't set in `.env`, or the sidecar container isn't running.

**Update started but the page never came back** — Open `http://localhost:4420` on the Docker host, or `http://fiestapi.local:4420` on a FiestaPi, again after a minute. From another device on a standard Docker install, use the host's IP address. If it's still down, check logs: `docker logs fiestaboard`. Before recreating the service, confirm its image and data mounts match the intended installation. See [Recovery options](/docs/setup/v11-upgrade#recovery-options) if the failure followed a version change.

**I joined the beta but came back on stable** — The updater installs the selected
channel image while your Compose file may still name Stable. A later recreation
can therefore start a different image, and the hub may reapply its saved channel
at startup. Check the running version, Compose image and saved channel together.
For an outdated updater, pull and recreate the `fiestaupdater` service using your
actual Compose file; see [FiestaUpdater](/docs/deployment/fiestaupdater). Do not
use repeated restarts as proof that a channel switch succeeded.

**I want to roll back** — Follow [Recovery options](/docs/setup/v11-upgrade#recovery-options). Channel return, snapshot rollback and manual recovery have different image and data behavior. A partial settings restore or an accepted updater request is not proof that the old image booted.
