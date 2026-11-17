---
sidebar_position: 11
description: "What is available in the FiestaBoard 11 Alpha preview, how to find familiar controls, and what to check before trying it."
keywords: [FiestaBoard 11, v11, alpha preview, onboarding, upgrade, universal UI]
---

# Try the FiestaBoard 11 Preview

FiestaBoard 11 is an **Alpha preview**, not the Stable or Beta release. This guide describes the published **11.0.0-alpha.4** checkpoint checked on **November 17, 2026**. Later work on the `v11` branch is not necessarily in that image.

For everyday use, stay on Stable. To explore the preview, use a separate test installation and test data. To carry existing data into it, first read [Upgrading to v11 and recovering 10.x](/docs/setup/v11-upgrade). The real-image upgrade and restore gate is still incomplete; publication of an Alpha image is not a claim that those recovery scenarios passed.

## What is new in this preview?

- **Navigation that adapts to the screen.** Home, Pages, Schedule and Displays use bottom navigation on a phone and a navigation rail on wider screens. More contains destinations such as Integrations and Settings; Collections live under Pages.
- **A clearer Home screen.** Compose writes a message; Change Page selects a saved page. Temporary overrides have a duration and countdown. Check the selected display before sending anything.
- **Readable board previews.** Actual size is the default. A wide board scrolls horizontally instead of shrinking its tiles to fit. Use **Fit** for an overview of the whole board.
- **Collection ordering and editor shortcuts.** Reorder a Collection's pages with its sortable list. Press `?` outside a text field in the page editor to see its keyboard shortcuts.
- **Clearer connection state.** Home reports display health and silence. The installable web app can show a last-known board when the hub is unreachable; that is cached information, not confirmation of what is showing now. Signing out clears its private offline data. Installation support depends on the browser and a secure connection.
- **Explicit release channels.** The v11 preview has a Stable / Beta / Alpha chooser. Returning to an older channel can discard changes made after the recovery snapshot. Read [Release Channels](/docs/features/release-channels) before switching.

This is a checkpoint of the redesign, not the finished universal UI. The new touch editor, complex editing and Creator IDE screens, full setup redesign, and remaining Settings, Schedule, Displays and Integrations layouts are not all in alpha.4. Backend support for a feature does not mean its planned screen or native app has shipped.

Built-in hub HTTPS and the web push backend are included from **11.0.0-alpha.4**. HTTPS is opt-in; see [built-in HTTPS setup](/docs/deployment/production#built-in-https) for certificate and listener configuration. The web push backend supports browser enrollment and test delivery, but automatic event alerts and the notification settings screen are not included in this checkpoint.

## Before you start

- Have a working Docker installation using the [Docker setup guide](/docs/setup/docker-setup), or SSH access to your FiestaPi and its install directory.
- Keep the current installation's Compose files, environment settings, image identity and data separate from a test installation. Two instances must not write to the same data directory or drive the same real display at once.
- Keep an off-device backup. For existing data, use the [backup preparation and scope checklist](/docs/setup/v11-upgrade#before-changing-images).
- Home Assistant add-ons are updated by the Supervisor. These Docker preview instructions do not supply an Alpha add-on or authorize replacing its managed image.

## Get the preview

Stock Stable **10.3.3** and Beta **10.3.4-beta.0** do not offer Alpha in their channel controls. Joining that Beta will not unlock it. The 10.x chooser backport is still a candidate; see [which controls are available](/docs/features/release-channels#which-controls-will-i-see).

For a separate Docker test installation, follow the normal Docker setup, using a separate install directory, Compose project/container names, host port and persistent directories. Before its first start, set the FiestaBoard service's image to:

```yaml
image: fiestaboard/fiestaboard:v11-alpha-11.0.0-alpha.4
```

This exact-version tag selects the documented checkpoint. The moving tag `v11-alpha` can select a newer preview. Existing installations must follow the [plain image-swap procedure](/docs/setup/v11-upgrade#plain-image-swap) instead of starting over or sharing live files.

## First checks after signing in

1. Open **Settings → System** and confirm the version is the one you selected. Reconnect or reload the page if it still shows the old interface.
2. Select the intended display on Home. Check its status before using Compose or Change Page; use a test display for your first send.
3. Open Pages, a Collection and the Schedule. Confirm the content, ordering, timing and time zone you expect.
4. Check Integrations and reconnect any provider that asks you to sign in. A restored configuration does not include portable OAuth credentials.
5. Test the actions you rely on, then restart once and repeat the checks. A successful start alone does not prove an upgrade, persistent data or recovery path.

If something fails, stop editing the affected data and follow [recovery](/docs/setup/v11-upgrade#recovery-options). Include the exact image/version, installation type, steps and redacted logs in a report. Do not attach backups, environment files, cookies or provider tokens.

## What still blocks Beta and Stable?

At this checkpoint the owner still needs release and runtime evidence: a published 10.x chooser bridge and its reachable upgrade path; real backup, upgrade, managed return and manual recovery tests; and the remaining required feature, hardware, security and visual reviews.

Promotion also needs release guards and update discovery that accept v11 Beta/Stable, a tested forward Alpha-to-Beta policy, and a published stable FiestaUI dependency. Existing Alpha-to-Beta controls return to **10.x** and restore old configuration; they are not a promise to preserve preview work in a future v11 Beta. Release owners must authorize and verify each publication separately. No Beta or Stable release date is promised here.
