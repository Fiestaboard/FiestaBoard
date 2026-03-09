---
sidebar_position: 16
description: "Display real-time Disney theme park ride wait times on your split-flap display with FiestaBoard."
keywords: [FiestaBoard Disney, theme park wait times, Disneyland, Disney World, ride queue times, split-flap Disney]
---

# Disney Parks Queue Times

Display real-time ride wait times from Disney theme parks worldwide. **No API key required.**

<BoardScreenshot src="/img/disney-parks-times-display.png" alt="Disney Parks wait times on split-flap board" />

## Overview

The Disney Parks plugin shows:

- Live ride wait times from any Disney park
- Select specific rides to monitor
- Supports Disneyland, California Adventure, and all Walt Disney World parks

## Setup

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Disney Parks Queue Times** on
4. Select your park and choose rides to monitor
5. Click **Save Changes**

:::tip
Data comes from Queue-Times.com -- no API key or account needed.
:::

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{disney_parks_times.formatted}` | Formatted wait times display | `SPACE MTN 45 MIN` |

The plugin also provides array variables for iterating over parks and rides in advanced templates.

## Supported Parks

- Disneyland (Anaheim)
- Disney California Adventure
- Magic Kingdom (Walt Disney World)
- EPCOT
- Hollywood Studios
- Animal Kingdom

## Next Steps

- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
- [Page Editor](/docs/features/page-editor) -- Create layouts with plugin data
