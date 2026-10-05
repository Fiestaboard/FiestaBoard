# FiestaPanel Setup Guide

Turn any TV or browser into a FiestaBoard display.

## Overview

**What it does:** FiestaBoard draws your pages as a full-screen board, and a TV app or browser tab shows it.

**Prerequisites:**

- FiestaBoard running on your network
- A TV with the FiestaBoard app, or any device with a web browser

## Quick Setup

1. **Enable:** the FiestaPanel output ships with FiestaBoard. In the setup wizard choose **FiestaPanel**, or create a panel under **Settings → Panels**.
2. **Configure:** give the panel a name and the screen's size; FiestaBoard sizes the grid to fit.
3. **Template:** choose a look (split-flap or LED matrix) and a page to show.
4. **View:** open the panel's link on the TV or in a browser.

## Template Variables

| Variable | Description |
|----------|-------------|
| None | An output plugin adds no template variables: it shows what your pages render. |

## Configuration Reference

| Setting | Required | Description |
|---------|----------|-------------|
| Shape (`device_type`) | Yes | `panel` for a panel sized from its screen; `flagship`, `note` or `note_array` to imitate a Vestaboard. |
| Grid (`grid_rows`, `grid_cols`) | For `panel` | 3–96 rows by 15–128 columns. |
| Notes (`notes_wide`, `notes_tall`) | For `note_array` | The array's size in Notes. |

There are no environment variables.

## Troubleshooting

**The panel shows nothing**
- Make sure a page is active for the panel's board, and that the board is not paused.
- Reload the panel's link.

**The panel shows the old size after changing the TV**
- FiestaBoard never serves a frame of the old shape; the next refresh draws the new one.
