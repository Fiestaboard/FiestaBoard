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

The default **Through black** fade uses six pixel frames over approximately one second. It looks stepped and leaves the device's brightness setting alone while the picture dims. **Blend** cross-fades the two pages. A configured brightness is applied after the new page arrives.

### Using the Divoom App Too

If a script or another tool uploads a picture to the Pixoo, FiestaBoard notices that the Pixoo's picture count moved past its own and sends your page again. Whether the Divoom app's own uploads move that count hasn't been confirmed yet. If the Pixoo restarts, or a tool resets the count before uploading (most Pixoo scripts do), FiestaBoard can't tell the two apart and always sends your page again, even with **Restore automatically** off.

Use one FiestaBoard display per Pixoo. Two displays, or two FiestaBoard installs, pointed at the same Pixoo each see the other as another app.

To let another app keep the Pixoo, turn off **Restore automatically** in the display's settings. FiestaBoard then shows a notice with a **Restore** button instead of taking the Pixoo back.

FiestaBoard can't see every change. If an app switches the Pixoo to another channel, such as its clock, without uploading a picture, no notice appears. Call `POST /v1/boards/{board}/restore` to put your page back. See [Saving what another app put on the board](../features/page-editor.md#saving-what-another-app-put-on-the-board).

### Mounting

Mounted the Pixoo sideways or upside down? Set **Orientation** in the display's settings to rotate the picture to match.

## Troubleshooting

| Symptom | What to check |
|---|---|
| **Find my Pixoo** finds nothing | Make sure the Pixoo is on the same network as FiestaBoard, then type its IP address instead. |
| The Pixoo shows its clock instead of your page | Nothing has been sent yet. Give the display an active page. |
| Text is cut off | The page is wider or taller than the grid: 10 columns × 8 rows at Large. Pick this display in the page editor's size picker, or switch to Small. |
| The Pixoo shows another channel after you used the Divoom app | Switching channels doesn't upload a picture, so FiestaBoard can't tell. Call `POST /v1/boards/{board}/restore` to put your page back. |
| The display stopped updating | The Pixoo's IP address changed. Reserve a fixed address in your router, then update it in the display's settings. |

### Discovery and Manual Setup

If **Find my Pixoo** reports a container network such as `172.18.0.0/24`, open FiestaBoard using the Pi's LAN IP address, or enter your LAN network in **Network to search**. Opening FiestaBoard through a hostname such as `fiestapi.local` does not supply an IP-based network hint.

You can also choose **Enter address manually**, enter the Pixoo's address, complete **Test connection**, and save the display. Entering an address in **Network to search** runs discovery against that address; it does not complete manual setup.

Local discovery probes HTTP port 80 at `/post`. Seeing `:80` in its error does not by itself indicate a browser cache problem. If your device uses a different API endpoint, discovery will not find it: enter the complete address in **Device address**, including its port and path (for example `http://192.168.1.50:9000/divoom_api`), then use **Test connection**. Use the endpoint appropriate to your device; the example is not a guarantee for every Pixoo firmware. Current plugin versions preserve explicit endpoints, while older installed copies may discard the path. Check for a Divoom plugin update if manual setup still contacts the wrong endpoint.

**Ask Divoom's servers** can fill in a device address even when FiestaBoard cannot reach that device locally. Follow it with **Test connection**, save, and send a page. If discovery fails but manual setup works, include that distinction when reporting the problem.

### Updating an Existing Beta Installation

Updating FiestaBoard's image does not replace an already-installed Divoom plugin. After updating FiestaBoard, open **Integrations**, choose **Check for updates**, and apply the Divoom plugin update if offered. Then send a page and check the display's brightness, including when you interrupt a fade by sending another page.

Installed display plugins are eligible for update checks even before you save your first board. With plugin auto-updates enabled, FiestaBoard checks five minutes after startup and then hourly. Incompatible updates remain held back with an explanation. If the installed FiestaBoard version predates this behavior, a display plugin with no saved board using it may have been skipped.

The cancellation fix is included in the bundled plugin commit `863ab740a23db02e4274e52f23a3b0a815c4526e`. Both the previous bundled copy and this fix declare plugin version `0.6.0`, so that version label alone does not confirm that the fix is installed. Plugin update checks compare repository commits.

For the bundled settings and actions, see the [pinned plugin manifest](https://github.com/Fiestaboard/fiestaboard-output--divoom-pixoo/blob/863ab740a23db02e4274e52f23a3b0a815c4526e/manifest.json). The plugin's older setup guide still describes a manual beta installation; v10 bundles the plugin.
