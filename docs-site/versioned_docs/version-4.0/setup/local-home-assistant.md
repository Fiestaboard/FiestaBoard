---
sidebar_position: 3
description: "Run Home Assistant in Docker for local development so the FiestaBoard dev container can connect and test the Home Assistant plugin."
keywords: [FiestaBoard development, Home Assistant, local testing, Docker, dev container]
---

# Local Home Assistant for Development

Use this setup to test the [Home Assistant plugin](/docs/plugins/home-assistant) locally without a real Home Assistant server. The FiestaBoard dev container connects to a Home Assistant container on the same Docker network.

**This is for local development only.** Only the FiestaBoard dev container is intended to talk to this Home Assistant instance.

## Prerequisites

- [Local development environment](/docs/setup/local-development) (Docker Compose with `docker-compose.dev.yml`)
- Enough disk and memory for the Home Assistant image (~1GB+)

## Start the dev stack with Home Assistant

Run both the FiestaBoard dev stack and the optional Home Assistant service:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.ha.yml up -d
```

- **FiestaBoard**: http://localhost:4420  
- **Home Assistant**: http://localhost:8123 (on the host; create your token and configure entities here)

From inside the FiestaBoard container, Home Assistant is reachable at **http://homeassistant:8123**.

## First-time login (no default password)

Home Assistant does **not** ship with a default username or password. The first time you open http://localhost:8123 you will see **Create account**: choose a name, username, and password.

**Suggested for local dev only:** when creating the account, use something easy to remember, e.g. username `dev` and password `dev`. (Do not use these on a real or exposed instance.)

If you already completed setup and forgot the password, you can reset and create a new account by removing the config volume (see [Data persistence](#data-persistence)) and opening http://localhost:8123 again.

## Configure FiestaBoard to use local Home Assistant

1. **Create a long-lived access token in Home Assistant**
   - Open http://localhost:8123 and sign in (using the account you created above).
   - Go to **Profile** (your user, bottom left) → **Long-Lived Access Tokens**.
   - Create a token and copy it.

2. **Point FiestaBoard at the local HA container**
   - In your project `.env`, set:
     - `HOME_ASSISTANT_BASE_URL=http://homeassistant:8123`  
       (Use the hostname `homeassistant` so the **container** can resolve it; do not use `localhost`.)
     - `HOME_ASSISTANT_ACCESS_TOKEN=<your_long_lived_token>`
   - Or configure the same URL and token in the FiestaBoard UI: **Integrations** → **Home Assistant** → enable and enter URL and token.

3. **Restart the FiestaBoard container** if you changed `.env`:
   ```bash
   docker compose -f docker-compose.dev.yml -f docker-compose.ha.yml restart fiestaboard
   ```

You can now use the Home Assistant plugin and entity picker in the UI; the dev container will talk to the local Home Assistant container.

## Optional: MQTT so HA discovers FiestaBoard as a device

To have FiestaBoard appear as a controllable device in Home Assistant (switches, sensors, buttons), enable MQTT in your `.env`:

- `MQTT_ENABLED=true`
- `MQTT_BROKER_HOST=mosquitto` (use hostname `mosquitto` when using `docker-compose.ha.yml`)

Then restart the FiestaBoard container. After configuring the MQTT integration in HA to use the Mosquitto broker (Settings → Add integration → MQTT → broker `mosquitto`, port `1883`), the FiestaBoard device and all its entities will appear automatically.

## Stopping Home Assistant

To stop only Home Assistant and keep the dev stack running:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.ha.yml stop homeassistant
```

To bring it back:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.ha.yml start homeassistant
```

## Data persistence

Home Assistant data (config, entities, token usage) is stored in a Docker volume `homeassistant-config`. It persists across container restarts. To reset:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.ha.yml down
docker volume rm fiestaboard_homeassistant-config  # exact name may vary by project name
```

Then start again; Home Assistant will go through first-time setup again.
