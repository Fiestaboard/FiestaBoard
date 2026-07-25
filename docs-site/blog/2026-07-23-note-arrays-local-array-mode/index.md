---
title: "FiestaBoard Catch-Up: Note Arrays, Home Assistant, and Now Fully Local Arrays"
description: "A recap of the last few releases: run multiple Vestaboard Notes as one logical display, a Home Assistant Supervisor add-on in beta, and a new fully local array mode with LAN-only updates."
slug: note-arrays-home-assistant-local-arrays
authors: [team]
tags: [release]
image: ./social-card.png
---

It's been a while since we posted an update, so here's a recap of what's shipped over the last few releases, plus the big one that just landed.

<!-- truncate -->

## Multi-board arrays (v4 schema)

The headline feature from a few releases back: you can now run multiple Note boards as a single logical display. Arrays go from simple side-by-side pairs up to an 8x8 grid, with five ready-made presets (2 or 4 side-by-side, 2 or 4 stacked, 2x2) or fully custom layouts. A few things that made this less painful than it could've been:

- **Auto-detect** — the settings UI can read your live board and figure out its type and size for you
- **Smarter previews** — variable-size rendering with visible seams between Notes, a board-size indicator, and a fit-to-width/actual-size toggle for wide arrays
- **Size-aware plugins** — plugins now get real board dimensions, so content can adapt to whatever layout you're running
- **Everything that switches between boards** — scheduling, page loading, page triggering — got rebuilt to be dimension-driven instead of assuming a single fixed board

The fun engineering problem here: none of us own a wall of eight Vestaboards to test against. So we built a local mock Cloud API with a live web UI that simulates split-flap tiles, message history, and arbitrary board configs on the fly. That's what let us test odd array shapes we'll probably never own in real life.

This bumped the schema from v3 to v4, but existing pages migrate automatically and single-board setups (Flagship or Note) work exactly as before.

## Since then: v6.16.2 highlights

- **Collections** (formerly "Carousels") now support variable-driven page selection, so what shows can depend on live data
- **Schedule overrides** — pin a specific page to a specific date, useful for holidays or one-offs
- Inline schedule enable/disable toggles
- More Date/Time plugin formatting options
- A `ZEROPAD` template filter for padding numbers (7 → 07)
- A **Home Assistant Supervisor add-on**, now in beta with docs, plus fixes so the UI behaves correctly behind HA Ingress

On that last point — if you're running FiestaBoard alongside Home Assistant, we'd like that integration to be genuinely good, not just functional. If you've got ideas, run into friction, or want to contribute, that's an area where community input would go a long way right now.

## And today: Local Array Mode

Arrays could already run over Vestaboard's cloud API, but as of this release they can run entirely over your local network — no cloud round-trip required. The missing piece wasn't talking to the boards, it was the arrangement layer: knowing where each Note sits in the grid and splitting each frame into the right slice for the right board. FiestaBoard now cuts each frame into 3x15 pieces and fans them out to your Notes over LAN. That gets you:

- Messages that never leave your network
- Lower latency and no cloud rate limit
- Transition animations on arrays (previously cloud-only)
- **Identify mode** — flash each slot's position number on the physical boards, handy when wiring up a new array
- Network scanning, per-tile connection tests, and duplicate-IP warnings for debugging a multi-board setup

Cloud arrays aren't going anywhere — this is opt-in, and cloud stays the default for new arrays.

Setup guide: [Note Arrays](/docs/setup/note-arrays)

Full changelog: https://github.com/Fiestaboard/FiestaBoard/releases

Happy to answer questions on [GitHub](https://github.com/Fiestaboard/FiestaBoard/issues) or [Discord](https://discord.gg/JvN8y6ahaf) — and if you're on Home Assistant, genuinely curious what would make that integration better for you.
