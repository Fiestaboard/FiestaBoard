---
sidebar_position: 3
description: "Show FiestaBoard pages on an LED matrix. Set up a Divoom Pixoo 64 over your Wi-Fi, choose its text size, and learn how pages look in pixels."
keywords: [LED matrix display, Divoom Pixoo 64, Pixoo dashboard, Pixoo 64 FiestaBoard, RGB LED display, pixel display, LED sign dashboard]
---

# LED Matrices

:::note Version availability
These instructions describe FiestaBoard v10 (`next` / beta). The output-plugin setup and Divoom Pixoo 64 support are not available in stable v9. Native Apple TV and Android TV apps are coming soon; use a browser for TV viewing.
:::

FiestaBoard can draw your pages on an LED matrix: a grid of bright RGB pixels. LED matrices show things a split-flap board can't, like colored text, lowercase letters, icons, and pixel art. Pages change with smooth transitions such as wipe, slide and dissolve.

## Supported Devices

| Device | Grid | Connection |
|---|---|---|
| **Divoom Pixoo 64** | 64 × 64 LEDs: 8 rows × 10 columns of text at Large, 10 × 16 at Small | Directly over your Wi-Fi |

The bundled plugin declares only the Pixoo 64. Pixoo 16, Pixoo 32 and other Divoom models are not supported or validated by this guide. Hardware timing was measured on a Pixoo 64; other firmware may behave differently.

Support for other LED panels requires a compatible [output plugin](/docs/development/output-plugins) and validation on that hardware.

## Before You Start

- Set the Pixoo 64 up with the Divoom app and connect it to your Wi-Fi.
- FiestaBoard and the Pixoo must be on the same network.
- FiestaBoard's local discovery and display delivery need no Divoom cloud service. The optional **Ask Divoom's servers** action contacts Divoom and exposes your public IP address; it is not required.

## Set It Up

1. In the setup wizard, pick **Divoom Pixoo 64**. If FiestaBoard is already set up, open **Displays**, click **Add a display**, and pick **Divoom Pixoo 64**.
2. Give the display a name.
3. Click **Find my Pixoo** to search your network, or type the Pixoo's IP address. You can find the address in the Divoom app under the device's settings, or in your router's list of connected devices.
4. Click **Test connection**, then save.

The first page can take about a second to appear while the Pixoo switches away from its clock face. After that, pages arrive in about half a second.

:::tip Keep the address from changing
Reserve a fixed IP address for the Pixoo in your router. Otherwise the address can change after a power cut and FiestaBoard loses the device.
:::

## How Pages Look on an LED Matrix

| On the page | On the Pixoo |
|---|---|
| Letters, digits, punctuation | White pixel letters on black. Lowercase is kept. |
| Color tiles (`{63}` to `{68}`) | Solid red, orange, yellow, green, blue or violet cells |
| Colored text (`{red:HOT}`) | Letters in that color |
| Icons (`{icon:sun}`) | The icon's picture |
| Pixel canvases | Drawn pixel for pixel over the text |

### Text Size

Choose **Text size** on the display's settings page:

- **Large** (5×7-pixel letters, 8 rows × 10 columns) is the easiest to read across a room. New displays start here.
- **Small** (3×5-pixel letters, 10 rows × 16 columns) fits more text, and pages made for a Vestaboard Note fit as they are. Use uppercase at this size, because small lowercase letters are hard to tell apart from a distance.

Changing the text size resizes the display, and FiestaBoard lays its pages out again on the new grid.

### Transitions

Pick a transition in the display's settings: flip, slide, wipe, cascade, dissolve, fade, or none. The Pixoo shows about five frames a second, so a flip looks like a quick, stepped scramble that takes two to three seconds.

### Mounting

Mounted the Pixoo sideways or upside down? Set **Orientation** in the display's settings to rotate the picture to match.

## Troubleshooting

| Symptom | What to check |
|---|---|
| **Find my Pixoo** finds nothing | Make sure the Pixoo is on the same network as FiestaBoard, then type its IP address instead. |
| The Pixoo shows its clock instead of your page | Nothing has been sent yet. Give the display an active page. |
| Text is cut off | The page is wider or taller than the grid: 10 columns × 8 rows at Large. Pick this display in the page editor's size picker, or switch to Small. |
| The display stopped updating | The Pixoo's IP address changed. Reserve a fixed address in your router, then update it in the display's settings. |

For the bundled settings and actions, see the [pinned plugin manifest](https://github.com/Fiestaboard/fiestaboard-output--divoom-pixoo/blob/3819a91e2637829b28ab83b03d13acc5cf6e1e76/manifest.json). The plugin's older setup guide still describes a manual beta installation; v10 bundles the plugin.
