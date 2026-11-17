---
sidebar_position: 12
description: "Prepare a 10.x installation for the v11 Alpha preview, understand backup limits, and recover compatible data and images without relying on an unshipped chooser."
keywords: [FiestaBoard 11 upgrade, v11 rollback, backup, restore, Docker, FiestaPi, sessions]
---

# Upgrading to v11 and Recovering 10.x

This guide covers the **11.0.0-alpha.4** preview and published **10.3.3 / 10.3.4-beta.0** as checked on **November 17, 2026**. Alpha is for testing. The production-image upgrade, updater and restore scenarios remain **unverified at runtime**; the procedures below describe source behavior and operator recovery requirements, not a completed release qualification.

The published 10.x builds do **not** have the Alpha chooser. The [chooser backport (#2492)](https://github.com/Fiestaboard/FiestaBoard/pull/2492) is an unpublished candidate. Candidate testing and a released, reachable chooser are separate gates. Read [Release Channels](/docs/features/release-channels) and [what is new](/docs/setup/v11-preview) first.

## Before changing images

1. **Arrange recovery access.** Have SSH or console access to the Docker host, your account password, a maintenance window and enough free space for a separate backup and both images. Record the actual install directory, Compose file/project, service name, mounts and environment overrides. The examples below use the Docker Hub install in `~/fiestaboard` with `docker-compose.hub.yml`; on FiestaPi use `/opt/fiestaboard` and its `docker-compose.yml`. Adapt every command consistently.
2. **Record the running version and image.** Save the image reference, image ID and repository digest outside the install directory. Moving tags such as `latest` can change between backup and recovery. Do not treat a tag name alone as proof of what booted.
3. **Export a portable backup.** In **Settings → System → Backup**, choose **Export backup**. Verify the downloaded JSON is readable and contains the expected pages, settings, collections, schedules and displays. Keep it off the hub. Backups contain API keys and board credentials in plain text; keep them private.
4. **Prepare a complete stopped backup for manual recovery.** On an authenticated hub, use **Settings → Account → Signed-in devices → Sign out everywhere**. Do not sign in again or enroll devices before stopping the hub and taking the copy. Pause other users and enrollment attempts. This makes the saved session registry a signed-out baseline. It does not erase accounts, passwords, MCP tokens or provider credentials.
5. Stop the FiestaBoard service and copy **all** of its persistent data, external plugins, Compose files, `.env` if present, and any separately mounted certificates or configuration. A stopped copy includes SQLite journals consistently. Store the copy outside the live directories and off-device; verify it can be read before proceeding. Keep the original copy unchanged.

For the standard bind-mounted Docker Hub layout, a stopped-directory copy can look like this. Choose a new backup path and include any additional mounts identified above:

```bash
cd ~/fiestaboard
docker inspect fiestaboard --format '{{.Config.Image}} {{.Image}}'
docker image inspect "$(docker inspect fiestaboard --format '{{.Image}}')" \
  --format '{{json .RepoDigests}}'
docker compose -f docker-compose.hub.yml stop fiestaboard

# Use a NEW private directory; save the identity output there too.
mkdir -m 700 ../fiestaboard-before-v11
cp -p docker-compose.hub.yml ../fiestaboard-before-v11/
if [ -f .env ]; then cp -p .env ../fiestaboard-before-v11/; fi
sudo cp -a data ../fiestaboard-before-v11/
if [ -d external_plugins ]; then
  sudo cp -a external_plugins ../fiestaboard-before-v11/
fi
```

For named volumes or a different data path, use an equivalent stopped-volume backup instead of copying an unrelated `./data`. Do not continue after a failed or incomplete copy. A snapshot that lives only on the same failing disk is not a recovery plan.

## What each backup protects

| Backup | Included | Important limits |
| --- | --- | --- |
| Export backup; chooser/update snapshot | `config.json`, `settings.json`, `pages.json`, `collections.json`, `schedules.json`, `panels.json`; installed-plugin metadata | Not a full installation copy. Missing stores can be represented as null. Ordinary update snapshots are best effort; a newer-major chooser switch requires a successful strict backup. |
| Boot-time snapshot after a plain image swap | Config, settings, pages, collections and schedules, before normal store loading | No panels; empty installed-plugin metadata. Created only when the boot snapshot conditions apply. Not the same as a channel-join snapshot and not a substitute for your own backup. |
| Complete stopped-directory/volume copy | Everything in the paths you actually copy, including auth, OAuth and history files in the data directory | External plugin code, environment settings and separate mounts need their own copies. Restoring old authentication/provider files can restore old credentials and revocation state. |

Portable backups and chooser snapshots omit authentication accounts and sessions (`auth.json`, `auth_sessions.sqlite3`, `.session_key`), OAuth credentials and their key, hub identity/state outside the six files, and page draft, version and send-history sidecars. They do not contain plugin source code, your host environment or external certificates. These files may survive an image change because the same volume stays mounted; that is **preservation**, not backup coverage.

Portable import can attempt to reinstall missing external plugins from recorded metadata. It does not revert code already installed, and installs can fail or require manual work. Managed channel return/rollback explicitly skips plugin reinstall: configuration may roll back while newer plugin code remains. Check plugin compatibility afterward.

An import restores included stores in sequence, not as one transaction. Missing/null stores are skipped and existing destination data is left in place; omitted sidecars are not cleaned up. A failed import may have restored only some files. Check the result and its pre-restore copies before retrying. Importing onto a new empty installation does not recreate omitted accounts, OAuth connections or history. Reconnect providers as needed. A backup exported **after** an upgrade does not convert newer schemas back to 10.x.

## Plain image swap

Use this manual route for a controlled preview test when the installed 10.x build has no Alpha chooser. It needs the completed preparation above and does not depend on #2492 being published.

1. **Keep FiestaUpdater inactive for this manual preview.** After saving the original environment and Compose configuration, stop the updater if installed: `docker compose -f docker-compose.hub.yml stop fiestaupdater`. Remove `fiestaupdater` from `COMPOSE_PROFILES` in the live `.env` and any shell/service override, preserving other profile names and the token. Do not explicitly start that service. This also prevents the normal FiestaPi boot command from starting it again. Verify it stays stopped. The saved channel choice can otherwise make the hub automatically replace your chosen image, especially on a Beta installation. Preserve `.system-update.json` and its snapshot pointers; do not delete or hand-edit them.

2. Leave the hub stopped. In the existing Compose file, change the FiestaBoard service image to the chosen preview, preserving its data mounts, ports and remaining configuration:

   ```yaml
   image: fiestaboard/fiestaboard:v11-alpha-11.0.0-alpha.4
   ```

3. Pull that service, then recreate it from the same install directory and project:

   ```bash
   cd ~/fiestaboard
   docker compose -f docker-compose.hub.yml pull fiestaboard
   docker compose -f docker-compose.hub.yml up -d fiestaboard
   docker compose -f docker-compose.hub.yml logs --tail=100 fiestaboard
   ```

4. Sign in again and perform the [verification checks](#verify-the-result). Keep the 10.x copy unchanged. Avoid editing valuable data until the checks finish. Leave the updater disabled throughout this manual preview, including restarts; in-app updating and channel switching will be unavailable. Use manual pinned-image updates with a new compatible backup, or the manual return below. Do not enable the updater on a preview whose saved choice still names a different channel.

An ordinary image change keeps the same mounted data and normally retains valid sessions; this procedure deliberately revoked them to prepare a safer full-directory recovery baseline. Stock 10.3.3 and the listed Beta already have the session registry; they do not need its first-adoption logout again. A manual swap does not record a chooser join or guarantee that **Return to Stable/Beta** has the right snapshot. On a Pi, ensure the actual boot Compose configuration names the intended image; startup can reapply a saved channel choice. Verify again after a restart.

## If your build has the chooser

The published v11 preview includes it; current stock 10.x does not. A future released 10.x bridge must be verified before these steps are advertised for that installation.

With the updater enabled and reachable, open **Settings → System → Release channel**, select the destination, review its version, and confirm. For a newer major, the implementation takes a strict automatic backup before asking the updater to install. If the backup fails, switching is refused. Selecting a choice or cancelling confirmation does not install an image. Keep your downloaded backup even when an automatic snapshot exists; retained snapshots are limited and can be pruned.

The UI reconnecting or an API response saying `queued` is not enough: check the running version, image and data. Updater capability, readable-backup ordering and completed replacement still require the production runtime test gate.

## Recovery options

**Stop making changes when the preview fails.** Retain a separate copy of its current files and redacted logs for diagnosis. Do not let an older build write into a newer data directory whose compatibility has not been checked, delete newer files to make it boot, or overwrite your pre-upgrade copy.

### Managed return to Stable or Beta

Where available, the channel return restores its recorded join snapshot **before** requesting the older image and invalidates existing sessions. Accounts remain; users must sign in again. Alpha → Beta uses the snapshot from joining Alpha. Alpha → Stable uses the snapshot from leaving Stable; on a Stable → Beta → Alpha journey these can represent different dates and different data. Changes after the selected snapshot are lost from restored stores.

The destination is the channel's current moving `latest` or `beta` image, not necessarily your original image digest. Record and verify what actually boots. If the join snapshot is missing, the implementation can still request the older image with a warning; it has **not** restored compatible data. Use your known-good manual recovery instead of treating that warning as success. Plugin code, excluded sidecars and credentials are not reverted by this settings-only flow.

### Snapshot rollback

The system rollback API can restore a selected settings snapshot and request its recorded image identity. This differs from returning to a moving channel. Missing image metadata, an unsupported updater or a failed image step can leave **settings restored but the image unchanged**. Inspect the outcome and verify the running image; never assume a successful settings restore means the whole rollback completed.

### Manual recovery to your known-good 10.x installation

1. Keep other users and devices away from the hub during recovery. Stop FiestaUpdater if it is running and keep its Compose profile disabled as described in the manual swap procedure. While the newer hub is still usable, use **Sign out everywhere** again, then stop the service. Do not create another session before stopping. If the UI cannot run, keep access restricted and require fresh revocation after recovery before allowing clients back.
2. Move the failed live data and plugin directories aside; do not extract the baseline on top of them. Restore the complete stopped copy to the original mount paths with their permissions. Restore the matching environment/Compose configuration and any other copied mounts, but keep the updater profile disabled in the recovered live configuration until verification is complete. The saved `.env` may have enabled it. Use the **signed-out baseline** prepared above, not an arbitrary older authentication backup.
3. Set the Compose image to the recorded known-good immutable tag or digest. Restore its matching channel state from that baseline too; retaining the Alpha channel choice can cause startup to switch images again. Keep a copy of all current configuration before replacing it. Do not delete Docker volumes or run `down -v`.
4. Start only the FiestaBoard service from the original directory/project. Sign in with the restored account credentials, then use **Sign out everywhere** on the recovered installation before restoring general access. Sign in afresh and complete the checks below. This second revocation is especially important if the saved session state is uncertain. Users and TVs may need to sign in or pair again.
5. Re-enable the updater only after the recovered image, Compose image and baseline's saved channel agree. Inspect the baseline's `.system-update.json` locally without sharing its contents: if `channel` is present, it must match the running channel. No saved channel is valid for a stock installation that never opted in. If you cannot establish agreement, leave the updater disabled and update manually. To re-enable it after agreement, restore its profile setting, start the `fiestaupdater` service, and repeat the image/channel verification after a hub restart.

For the standard layout, after stopping and moving the live directories aside, the restore uses `sudo cp -a ../fiestaboard-before-v11/data ./data` and the same operation for `external_plugins` when it was saved. Confirm the destination directories do not already exist before copying, or you could create a nested or mixed restore. Then use `docker compose -f docker-compose.hub.yml up -d fiestaboard` with the recovered configuration and pinned image.

This returns data to the backup's point in time. Preview-only pages and edits are not merged. Password/account changes and MCP/OAuth secrets made later may also be reverted by a full copy; rotate or revoke credentials that must not become usable again, including at the provider. Session revocation alone does not revoke those secrets. See [Authentication](/docs/setup/authentication#upgrade-and-rollback).

If no compatible backup exists, return to the exact newer image that could read the data, with the original data preserved, and investigate there. Export for safekeeping, but do not assume that export is suitable for 10.x. Staying on the readable image or starting a separate clean 10.x installation is safer than forcing a schema downgrade.

## Verify the result

After either upgrade or recovery:

- Check **Settings → System**, container image ID and repository digest against your recorded target. Inspect startup logs for schema, migration, permission or plugin errors; do not share secret values.
- Confirm the original data mount is active. Compare display IDs/settings, pages, collections and ordering, schedules and time zone, silence settings and plugin configuration with the chosen baseline.
- Check accounts and sign-in behavior. After rollback, previously issued browser/TV sessions should be rejected. Reconnect provider accounts when required; verify integrations actually fetch data.
- Inspect page drafts/history separately if they matter. A core-store restore says nothing about those omitted sidecars. Check plugin code versions separately from restored configuration.
- Send a known test page to the intended display and check its real output. Verify scheduling and temporary override behavior you use.
- Restart once, then confirm the same image/channel, data and expected session behavior remain. A second boot catches channel reassertion and persistence problems that an initial page load misses.

The unresolved release gates are listed in [the preview guide](/docs/setup/v11-preview#what-still-blocks-beta-and-stable). These checks are your verification steps; this documentation does not claim the program has executed them successfully.
