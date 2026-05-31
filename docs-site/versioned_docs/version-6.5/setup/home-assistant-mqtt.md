---
sidebar_position: 5
description: "Connect FiestaBoard to Home Assistant via MQTT. Step-by-step guide to set up an MQTT broker, configure the HA MQTT integration, and enable MQTT in FiestaBoard."
keywords: [FiestaBoard MQTT setup, Home Assistant MQTT, Mosquitto broker, MQTT Discovery, home automation setup]
---

# Connecting to Home Assistant via MQTT

This guide walks you through everything needed to make FiestaBoard appear as a native device in Home Assistant — from setting up an MQTT broker to seeing FiestaBoard controls on your HA dashboard.

:::tip Already have an MQTT broker?
If you already use Zigbee2MQTT, Tasmota, ESPHome, or Frigate, you already have a broker. Skip to [Step 2: Enable the MQTT Integration in HA](#step-2-enable-the-mqtt-integration-in-home-assistant).
:::

## How it works

FiestaBoard uses [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) — the same protocol used by Zigbee2MQTT, Tasmota, and ESPHome. When MQTT is enabled, FiestaBoard automatically announces itself to Home Assistant by publishing discovery messages to the broker. No YAML config, no custom components, no restarts needed on the HA side.

The result: a **FiestaBoard device** appears in HA with switches, selects, sensors, and buttons you can use in automations and dashboards.

```
FiestaBoard ──────── MQTT broker ──────── Home Assistant
  (publishes state)   (Mosquitto)           (reads state,
  (reads commands)                           sends commands)
```

---

## Prerequisites

- A running FiestaBoard instance (v2.2+)
- Home Assistant (any install type: HAOS, Supervised, Container, or Core)
- Network connectivity between FiestaBoard, your MQTT broker, and Home Assistant

---

## Step 1: Set up an MQTT broker

An MQTT broker is the message relay between FiestaBoard and Home Assistant. You only need one broker for your whole home — if you already have one, skip ahead.

**Which situation applies to you?**

| Situation | What to do |
|-----------|------------|
| You use Zigbee2MQTT, Tasmota, ESPHome, or Frigate | You already have a broker. [Skip to Step 2.](#step-2-enable-the-mqtt-integration-in-home-assistant) |
| You run Home Assistant OS or Supervised | Install the Mosquitto add-on — takes about 2 minutes. See below. |
| You run Home Assistant Container or Core | Install Mosquitto on your server. See below. |

---

### Installing the Mosquitto add-on (HAOS / Supervised)

The Mosquitto broker add-on is a one-click install inside Home Assistant:

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Search for **Mosquitto broker** and click **Install**
3. Once installed, click **Start**, then enable **Start on boot** and **Watchdog**

That's it — the broker is running. Home Assistant will automatically detect it when you configure the MQTT integration in the next step.

**Optional: create a dedicated MQTT user**

By default, the Mosquitto add-on lets any Home Assistant user connect. For a cleaner setup, create a user specifically for MQTT clients:

- Go to **Settings → People → Users** → **Add User**
- Name it something like `mqtt` and set a password
- Use this username and password when configuring FiestaBoard

:::note
If you don't see the **Users** section, go to your Profile and enable **Advanced Mode** first.
:::

---

### Installing Mosquitto standalone (Container / Core / separate machine)

If you don't have the HA add-on store, install Mosquitto directly on your server:

```bash
# Debian / Ubuntu / Raspberry Pi OS
sudo apt update && sudo apt install -y mosquitto mosquitto-clients
```

Mosquitto 2.x only accepts local connections by default, so you need a small config file before FiestaBoard or Home Assistant (on other machines) can connect. Create `/etc/mosquitto/conf.d/fiestaboard.conf`:

**For a trusted home network (no password):**

```conf
listener 1883
allow_anonymous true
```

**With username/password authentication (recommended):**

```conf
listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd
```

Then create the user:

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd mqtt_user
# Enter a password when prompted
```

Restart Mosquitto to pick up the config:

```bash
sudo systemctl restart mosquitto
```

Note your broker's **IP address** (e.g. `192.168.1.100`), **port** (`1883`), and credentials if set — you'll need them in Step 3.

---

## Step 2: Enable the MQTT Integration in Home Assistant

Home Assistant needs to know about your broker before it can receive FiestaBoard's discovery messages.

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for and select **MQTT**
4. Enter your broker details:

   | Field | Value |
   |-------|-------|
   | **Broker** | IP or hostname of your MQTT broker |
   | **Port** | `1883` (default) |
   | **Username** | MQTT username (leave blank if anonymous) |
   | **Password** | MQTT password (leave blank if anonymous) |

5. Click **Submit** — HA will verify the connection

Once the MQTT integration shows **Connected**, Home Assistant is ready to receive FiestaBoard's discovery messages.

:::tip Mosquitto Add-on users
When using the Mosquitto add-on, the broker host from HA's perspective is `localhost` (or `core-mosquitto` from within the HA supervisor network). HA usually auto-detects the add-on — you may see a prompt to configure MQTT automatically when the add-on is running.
:::

---

## Step 3: Configure FiestaBoard

### Via the Settings UI

1. Open FiestaBoard at `http://<your-fiestaboard-ip>:4420`
2. Go to **Settings**
3. Find the **Home Assistant (MQTT)** section
4. Toggle **Enable MQTT** on
5. Enter your broker details:

   | Field | Value |
   |-------|-------|
   | **Broker Host** | IP or hostname of your MQTT broker (from FiestaBoard's perspective) |
   | **Broker Port** | `1883` |
   | **Username** | MQTT username (if your broker requires auth) |
   | **Password** | MQTT password (if your broker requires auth) |

6. Click **Save**

FiestaBoard will connect and immediately publish discovery messages. Within a few seconds, the FiestaBoard device will appear in HA.

---

### Via Environment Variables (Docker / headless)

Set these in your `.env` file or Docker Compose environment block:

```env
MQTT_ENABLED=true
MQTT_BROKER_HOST=192.168.1.100   # IP/hostname of your broker
MQTT_BROKER_PORT=1883
MQTT_USERNAME=mqtt_user           # leave blank if anonymous
MQTT_PASSWORD=mqtt_pass           # leave blank if anonymous

# Optional: the URL that appears as a "Visit" link on the FiestaBoard device page in HA
FIESTABOARD_EXTERNAL_URL=http://192.168.1.50:4420
```

Docker Compose example:

```yaml
services:
  fiestaboard:
    image: fiestaboard/fiestaboard:latest
    ports:
      - "4420:4420"
    environment:
      - MQTT_ENABLED=true
      - MQTT_BROKER_HOST=192.168.1.100
      - MQTT_BROKER_PORT=1883
      - MQTT_USERNAME=mqtt_user
      - MQTT_PASSWORD=mqtt_pass
      - FIESTABOARD_EXTERNAL_URL=http://192.168.1.50:4420
```

Restart the container after making changes.

---

## Step 4: Verify the connection

**In FiestaBoard:**
- Go to **Settings → Home Assistant (MQTT)**
- The status should show **MQTT Connected**

**In Home Assistant:**
1. Go to **Settings → Devices & Services → MQTT**
2. Look for a device named **FiestaBoard**
3. Click it — you should see all available controls and sensors

**Quick test:** Toggle the **Schedule** switch from the FiestaBoard device page in HA and confirm the schedule state changes in FiestaBoard's Settings page.

---

## Network considerations

FiestaBoard and Home Assistant need to **both reach the MQTT broker**. Common issues:

| Scenario | Solution |
|----------|----------|
| FiestaBoard is in Docker, broker is on the host | Use the host machine's LAN IP (e.g. `192.168.1.100`), not `localhost` |
| FiestaBoard and broker are in the same Docker Compose stack | Use the service name as the hostname (e.g. `mosquitto`) |
| Firewall blocking port 1883 | Open port 1883 on the machine running the broker |
| Using the Mosquitto HA add-on from an external FiestaBoard | Use the HA machine's LAN IP (e.g. `192.168.1.100`) as the broker host |

:::info Local dev setup
If you're running FiestaBoard with `docker-compose.ha.yml` for local development, the Mosquitto container is reachable from FiestaBoard as `mosquitto` and from HA as `mosquitto`. See the [Local Home Assistant development guide](/docs/setup/local-home-assistant) for full details.
:::

---

## Multiple FiestaBoards

If you have more than one FiestaBoard, give each a unique instance ID and base topic so they appear as separate devices:

```env
# Living room board
MQTT_INSTANCE_ID=fiestaboard_living_room
MQTT_BASE_TOPIC=fiestaboard_living_room

# Office board
MQTT_INSTANCE_ID=fiestaboard_office
MQTT_BASE_TOPIC=fiestaboard_office
```

Each board will appear as a separate device in Home Assistant.

---

## Next steps

Now that FiestaBoard is connected to Home Assistant, head to the [Home Assistant Control reference](/docs/features/home-assistant-control) for:

- Full list of controls and sensors available in HA
- Automation examples (welcome home messages, weather page switching, bedtime blanking)
- Dashboard card examples
- Troubleshooting entity-level issues
