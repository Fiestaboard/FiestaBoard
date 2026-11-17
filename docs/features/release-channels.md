---
sidebar_position: 11
description: "Choose between FiestaBoard Stable, Beta, and v11 Alpha previews, understand image tags, and check which channel controls your installed version supports."
keywords: [FiestaBoard release channels, stable, beta, alpha, v11 preview, Docker image tags, channel switching]
---

# Release Channels

Stay on **Stable** for everyday use. Choose **Beta** to try upcoming changes, or **Alpha** to explore the FiestaBoard 11 preview with a separate test installation and a recovery plan.

## Available versions

The published versions checked on **November 17, 2026** were:

| Channel | Version | Moving Docker tag | Exact-version Docker tag |
| --- | --- | --- | --- |
| Stable | `10.3.3` | `latest` | `10.3.3` |
| Beta | `10.3.4-beta.0` | `beta` | `10.3.4-beta.0` |
| Alpha | `11.0.0-alpha.5` | `v11-alpha` | `v11-alpha-11.0.0-alpha.5` |

All tags use the repository `fiestaboard/fiestaboard`. For example, the exact Alpha image is `fiestaboard/fiestaboard:v11-alpha-11.0.0-alpha.5`.

Moving tags follow new publications in their channel. Exact-version tags identify a particular published build; use one when you need to reproduce a preview or report a problem. Check the running version in **Settings → System** after an update.

The source branch names can be confusing: `main` publishes **Stable**, the branch named `alpha` publishes **Beta**, and `v11` publishes **Alpha**. Alpha previews have a Git tag such as `v11.0.0-alpha.5`, but deliberately have **no GitHub Release**. Their absence from the Releases page does not mean an Alpha image is unavailable.

## Which controls will I see?

**Stable 10.3.3 and Beta 10.3.4-beta.0 have Stable/Beta controls only.** You will not see an Alpha option there. Joining the currently published Beta does not add it. To try Alpha, follow the [v11 preview setup guide](/docs/setup/v11-preview).

The three-choice **Stable / Beta / Alpha** chooser is present in the published **11.0.0-alpha.5** source. The [10.x chooser backport, PR #2492](https://github.com/Fiestaboard/FiestaBoard/pull/2492), remained open at the November 17 checkpoint; its candidate had not been built or published. An open PR or successful CI does not add the feature to your installed release.

:::caution Preview availability and upgrade readiness
The Alpha image is published, but the production upgrade-and-restore check remains incomplete. Live channel switching, automatic backup before image replacement, and recovery have not passed that runtime gate. Read the [v11 upgrade and recovery guide](/docs/setup/v11-upgrade) before using Alpha with existing data.
:::

## Using the three-choice chooser

These steps apply to a build that includes the chooser, such as v11 Alpha. In-app switching requires the FiestaUpdater sidecar to be enabled and reachable. Home Assistant manages add-on updates separately and cannot switch channels through this control. See [In-App Updates](/docs/features/updating) for updater setup.

1. Export a backup from **Settings → System → Backup → Export backup** and keep it outside the installation. For an existing 10.x installation, first follow the [upgrade preparation steps](/docs/setup/v11-upgrade).
2. Open **Settings → System → Release channel**. Review the current channel and the version shown for each choice. If a version is unavailable, check connectivity and try again; it does not prove that the channel has no release.
3. Select a channel, then press the switch button. Selecting a card alone does not install an image.
4. Read the confirmation before proceeding. A move to a newer major version requires explicit confirmation; the implementation requires an automatic backup before requesting image replacement. **Cancel** leaves the switch unconfirmed.
5. After confirming, wait for FiestaBoard to reconnect, then verify the running version in **Settings → System**. An accepted update request alone does not establish that the new image booted.

## Returning from a preview

Returning to an older channel can restore the configuration captured before joining. Changes made after that snapshot may be lost. The return flow also signs out existing sessions. If the required snapshot is missing, the app warns that a manual restore may be necessary. See the [recovery instructions](/docs/setup/v11-upgrade) before switching back.

At the versions listed above, **Alpha → Beta returns to the 10.x Beta line**. It uses the restore path; do not use it expecting a forward upgrade that preserves work created in Alpha. A numeric v11 Beta or Stable release, and a tested forward Alpha → Beta migration, are not yet available through this release plan.

For manual image changes, follow the [v11 preview setup](/docs/setup/v11-preview) and [upgrade/recovery guide](/docs/setup/v11-upgrade). A manual image swap does not create the same channel-join recovery snapshot as an in-app switch.
