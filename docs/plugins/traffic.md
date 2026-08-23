---
sidebar_position: 4
description: "Show real-time commute and traffic times on your Vestaboard using FiestaBoard's Google Routes API plugin."
keywords: [FiestaBoard traffic plugin, Vestaboard traffic, Vestaboard commute, Google Routes API, commute time, traffic display, split-flap traffic, ETA]
---

# Traffic Plugin

Display commute times and live traffic conditions using the Google Routes API.

<BoardShot plugin="traffic" alt="Traffic display on split-flap board" />

## Overview

The Traffic plugin shows real-time driving times between configured origin and destination pairs. It supports up to 4 routes and multiple travel modes.

## Setup

### 1. Enable the Google Routes API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to **APIs & Services → Library**
4. Search for **Routes API** (not Directions API)
5. Click **Enable**

### 2. Set Up Billing

The Routes API requires billing to be enabled:

1. Go to **Billing** in Google Cloud Console
2. Link a billing account to your project
3. Check the current [Routes API pricing and free tier](https://developers.google.com/maps/documentation/routes/usage-and-billing) before you start. Google Maps Platform bills the Routes API on its own per-API free monthly allotment, so confirm the terms that apply to your account

> **Note:** Google retired its flat $200/month Maps Platform credit in 2025 in favor of per-API free tiers. Pricing and free-tier limits change over time — treat Google's billing page as the source of truth, not this doc.

### 3. Create an API Key

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → API Key**
3. (Recommended) Restrict the key to only the Routes API

### 4. Configure FiestaBoard

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle the **Traffic** plugin on
4. Enter your Google Routes API key
5. Click **Save Changes**

### 5. Configure Routes

In the Web UI Integrations page, configure your routes:

- **Route Name** - A label for the route (e.g., "To Work")
- **Origin** - Starting address
- **Destination** - Ending address
- **Travel Mode** - Drive, Bicycle, Transit, or Walk

## Travel Modes

| Mode | Description |
|------|-------------|
| `DRIVE` | Driving with live traffic conditions |
| `BICYCLE` | Cycling route |
| `TRANSIT` | Public transit |
| `WALK` | Walking route |

## Address Formats

You can use either format for origins and destinations:

| Format | Example |
|--------|---------|
| Full address | `123 Main St, Anytown, ST 12345` |
| Coordinates | `37.7749,-122.4194` |

:::tip
Using coordinates is faster and avoids geocoding errors. You can find coordinates by right-clicking on Google Maps.
:::

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{traffic.formatted}` | Formatted commute display | `TO WORK 25 MIN` |

## Costs

The Routes API is billed per request. With 4 routes updating every 5 minutes, you'd make about 35,000 requests/month.

| Item | Notes |
|------|-------|
| Per route request | Billed per request — see Google's [Routes API pricing](https://developers.google.com/maps/documentation/routes/usage-and-billing) |
| Free tier | Google applies a per-API free monthly allotment to the Routes API — check your account's current limit |

> **Note:** Estimate your monthly cost from your route count and refresh interval against Google's current Routes API rates and free tier. Google's pricing changes over time, so this doc doesn't hardcode a figure.

## Troubleshooting

### 403 Forbidden

- The Routes API is not enabled - go to Google Cloud Console and enable it
- Billing is not set up - link a billing account

### 400 Bad Request

- Check that your addresses are valid and complete
- Try using coordinates instead of addresses

### Rate Limiting

If you see rate limit errors:

- Increase the refresh interval
- Use coordinates instead of addresses (avoids geocoding calls)

## Next Steps

- [Plugins Overview](/docs/plugins/overview) - See all available plugins
- [API Keys](/docs/setup/api-keys) - Getting all required API keys
