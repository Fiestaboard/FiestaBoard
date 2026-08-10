---
sidebar_position: 4
description: "Install FiestaBoard as a Home Assistant Supervisor add-on. Sidebar Ingress, auto MQTT discovery, HA-managed backups — all from the HA Add-on Store. Currently in beta."
keywords: [FiestaBoard Home Assistant add-on, HAOS, Home Assistant Supervisor, Vestaboard Home Assistant, FiestaBoard HA app, supervised add-on, ingress]
---

# Home Assistant Add-on (Beta)

:::warning Beta — feedback wanted
The Home Assistant add-on is in **beta**. End-to-end install works (Ingress, MQTT auto-discovery, HA core API, backups, updates through the add-on store), but the wrapper is still maturing and we'd love to hear from you:

- 🐛 **Found a bug or have a suggestion?** [Open an issue](https://github.com/Fiestaboard/FiestaBoard-Home-Assistant-App/issues) on the add-on repo.
- 💬 **Want to chat or get help?** [Join us on Discord](https://discord.gg/JvN8y6ahaf) — there's a community of FiestaBoard users (including Home Assistant power users) happy to help.

Even "it just worked" reports are useful while we're stabilizing the beta — let us know what HA install type you're on (OS / Supervised) and which features you tried.
:::

If you already run **Home Assistant OS** or **Home Assistant Supervised**, you can install FiestaBoard from the HA Add-on Store. The add-on wraps the standard `fiestaboard/fiestaboard` image and adds the integration glue HA expects:

- **Sidebar entry via Ingress** — one-click web access from the HA sidebar, authenticated by HA itself.
- **Auto MQTT discovery** — works zero-config with the official **Mosquitto broker** add-on.
- **HA core API** — FiestaBoard's [Home Assistant plugin](/docs/plugins/home-assistant) talks to HA via the Supervisor proxy with no long-lived access token to create.
- **HA-managed backups** — FiestaBoard's `/app/data` (settings, plugin state, marketplace plugins) is mounted from HA's persistent `addon_config` volume, so HA snapshots capture everything.
- **Updates through the add-on store** — a weekly workflow in the add-on repo polls this repo for new releases and opens a sync PR. Once merged and tagged, HA Supervisor offers the update like any other add-on.

This is a different install path than [FiestaPi](/docs/setup/raspberry-pi) (a standalone Pi image) or [Docker Compose](/docs/setup/quick-start). Use the add-on if:

- You already have a Home Assistant OS / Supervised install.
- You want FiestaBoard updates to come through HA's UI alongside the rest of your add-ons.
- You want FiestaBoard's HA plugin and MQTT setup to be zero-config.

## What you'll need

- A working **Home Assistant OS** or **Home Assistant Supervised** install (the Add-on Store isn't available on Container or Core).
- Your **Vestaboard** and its API key ([how to find it](/docs/setup/api-keys)).
- A **Mosquitto broker** add-on installed (optional, but required for MQTT auto-discovery).

## Install

1. In Home Assistant, navigate to **Settings → Add-ons → Add-on Store**.
2. Click the **⋮** menu (top-right) → **Repositories**.
3. Add the repository URL:

   ```text
   https://github.com/Fiestaboard/FiestaBoard-Home-Assistant-App
   ```

4. The **FiestaBoard** add-on appears in the store. Click **Install**.

Or use the one-click badge in the add-on repo's [README](https://github.com/Fiestaboard/FiestaBoard-Home-Assistant-App):

[![Open your Home Assistant instance and show the app store with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_store.svg)](https://my.home-assistant.io/redirect/supervisor_store/?repository_url=https%3A%2F%2Fgithub.com%2FFiestaboard%2FFiestaBoard-Home-Assistant-App)

## Configure and start

Open the add-on's **Configuration** tab and set, at minimum:

- `board_api_mode`: `local` (recommended) or `cloud`.
- For local mode: `board_host` (your board's IP) and `board_local_api_key`.
- For cloud mode: `board_read_write_key`.
- `weather_api_key` and `weather_location` if you'll use the weather plugin.
- `timezone` (e.g. `America/Los_Angeles`).

Click **Start**, then **Open Web UI** when the add-on goes green. The remaining FiestaBoard plugins (transit, sports, surf, AI art, etc.) are configured from inside FiestaBoard's own web UI — the Configuration tab intentionally only surfaces the bootstrap-critical fields.

## How HA-specific behavior is handled

A couple of things work differently under the add-on compared to a standalone Docker install. The full reference lives in the add-on repo's [DOCS.md](https://github.com/Fiestaboard/FiestaBoard-Home-Assistant-App/blob/main/fiestaboard/DOCS.md); the highlights:

- **Auth defaults to off.** [FiestaBoard 6.0+ auth](/docs/setup/authentication) is gated behind HA Ingress, which already authenticates web access. Set the `fiestaboard_auth_enabled` option to `true` if you publish the LAN port (`4420`) to the internet or share it with people without HA logins.
- **The in-app "Update Now" button is hidden.** Updates flow through HA's add-on store, not FiestaBoard's own [in-app updater](/docs/features/updating). The companion [fiestaupdater](/docs/deployment/fiestaupdater) sidecar would race HA Supervisor's update flow and isn't safe under HA, so the shim disables it.
- **MQTT is auto-wired.** Install the Mosquitto broker add-on first; FiestaBoard picks up the broker host and credentials through the HA services API with no manual config.

## Help us shape the beta

This integration is new and we want your feedback — what works, what doesn't, what's confusing, what's missing. Two ways to reach us:

- 🐛 **[Open an issue on the add-on repo](https://github.com/Fiestaboard/FiestaBoard-Home-Assistant-App/issues)** for bugs, feature requests, or anything reproducible. Please include your HA installation type (OS / Supervised), the add-on version, and the relevant snippet from the add-on **Log** tab.
- 💬 **[Join our Discord](https://discord.gg/JvN8y6ahaf)** to chat, ask questions, share what you've built, or just say hi. There's a community of FiestaBoard users (including Home Assistant folks) happy to help.

### Where things live

| Concern | Repo / link |
| --- | --- |
| Add-on bugs, feature requests, install issues | [`FiestaBoard-Home-Assistant-App` issues](https://github.com/Fiestaboard/FiestaBoard-Home-Assistant-App/issues) |
| Add-on source and config docs | [`FiestaBoard-Home-Assistant-App`](https://github.com/Fiestaboard/FiestaBoard-Home-Assistant-App) ([DOCS.md](https://github.com/Fiestaboard/FiestaBoard-Home-Assistant-App/blob/main/fiestaboard/DOCS.md)) |
| FiestaBoard core (everything not HA-specific) | [`FiestaBoard` issues](https://github.com/Fiestaboard/FiestaBoard/issues) |
| Chat, help, show-and-tell | [Discord](https://discord.gg/JvN8y6ahaf) |
