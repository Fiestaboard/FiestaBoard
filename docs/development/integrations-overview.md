---
sidebar_position: 1
description: "Every way to build on FiestaBoard: push frames to a new display with an output plugin, pull frames onto any screen, bring data in with a data plugin, and read or drive boards through the v1 API and the MCP server."
keywords: [FiestaBoard integrations, FiestaBoard API, output plugin, frame stream, data plugin, MCP server, v1 API, build a display, developer overview]
---

# Building on FiestaBoard

FiestaBoard turns live data into pages and shows them on real-world displays. You can build on it at either end: put FiestaBoard on a new display, or feed it, read it and drive it from your own code. This page lists every way in and points to the guide for each.

## Which One Do You Need?

| You want to | Use | Guide |
|-------------|-----|-------|
| Show FiestaBoard on a device that FiestaBoard sends frames to: an LED matrix, a sign | **Push**: an output plugin | [Writing an Output Plugin](/docs/development/output-plugins) |
| Show a board on a screen you control, in any language, with no install | **Pull**: the frame endpoints | [Subscribing to Board Frames](/docs/development/output-stream-api) |
| Put new data on boards: a service, a sensor, a feed | **Provide data**: a data plugin | [Plugin Development Guide](/docs/development/plugin-guide) |
| Read what boards show, send messages, manage pages and schedules from a script | **Read and drive**: the v1 API | [API Endpoints](/docs/reference/api-endpoints) |
| Let an AI assistant read and drive FiestaBoard | **Read and drive**: the MCP server | [MCP clients](/docs/setup/authentication#mcp-clients-and-the-bearer-token) |

## Push: Write an Output Plugin

An output plugin is a Python package that drives one kind of device. FiestaBoard renders each page, decides when to send it, and hands your plugin a frame; your plugin sends it to the device. Core enforces the device's write rate, cancels stale writes, dedupes, and honors pausing and silence schedules, so the plugin only moves frames.

Choose push when the device has an API that FiestaBoard can reach, and you want it to behave like any other board: added in **Displays**, set up from its own settings screen, scheduled, previewed and transitioned.

[Writing an Output Plugin](/docs/development/output-plugins) covers the manifest, the plugin class, LED rendering, testing and publishing.

:::info Beta
Output plugins arrive with FiestaBoard 10.0.0 as a beta. Third-party output plugins run only while the **Third-party displays (beta)** switch in the **Integrations** page header is on; the outputs that ship with FiestaBoard need no beta.
:::

## Pull: Subscribe to Frames

Every board keeps the last frame it showed. Two public, read-only endpoints serve it through a panel: the panel's config and size, and the current frame as character codes, as text, and as rich cells with colors and icons when the board has them. Poll the frame every couple of seconds and draw it.

Choose pull when you control the display's software: a TV or kiosk browser, an ESP32 with a screen, a terminal dashboard. Nothing is installed in FiestaBoard, and the device needs nothing but HTTP. FiestaBoard's own TV viewer, [FiestaPanel](/docs/features/fiestapanel), works this way.

[Subscribing to Board Frames](/docs/development/output-stream-api) has the endpoints, the response fields, polling advice and a minimal viewer.

## Provide Data: Write a Data Plugin

A data plugin fetches data and exposes it as template variables, such as `{{weather.temperature}}`, that anyone can place on a page. It is the most common kind of plugin: weather, transit, stocks, calendars and home automation are all data plugins.

[Plugin Development Guide](/docs/development/plugin-guide) walks through one from idea to merged pull request. A plugin that reads a user's account on another service signs in through the platform: see [Signing In with OAuth](/docs/development/plugin-oauth).

## Read and Drive: The v1 API

The v1 REST API is the stable API for scripts and other software. Four nouns cover it: boards, pages, schedules and plugins. With it you can:

- send a one-off message to a board, and hand the board back to its schedule
- read what a board shows and why
- create, render and schedule pages
- read any plugin's current data

Every write reports what actually happened: whether the board changed, and if not, why. Start with [API Endpoints](/docs/reference/api-endpoints).

## Read and Drive: The MCP Server

FiestaBoard runs a Model Context Protocol server at `/api/mcp`, so an AI assistant such as Claude Desktop or Claude Code can look at boards, write pages and change schedules on your behalf. FiestaBot, the assistant built into the page editor, uses the same tools.

Connect a client with a bearer token: see [MCP clients and the bearer token](/docs/setup/authentication#mcp-clients-and-the-bearer-token).

## Home Automation

If you run Home Assistant, FiestaBoard can appear as a device over MQTT, with no code: [Home Assistant Control](/docs/features/home-assistant-control).

## Next Steps

- [Writing an Output Plugin](/docs/development/output-plugins)
- [Subscribing to Board Frames](/docs/development/output-stream-api)
- [Plugin Development Guide](/docs/development/plugin-guide)
- [API Endpoints](/docs/reference/api-endpoints)
