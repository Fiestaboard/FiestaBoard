---
sidebar_position: 2
description: "Connect a Vestaboard Flagship, Note, or Note array to FiestaBoard through Vestaboard's official Local API or Cloud API."
keywords: [Vestaboard setup, Vestaboard Flagship, Vestaboard Note, Note array, split-flap display, Vestaboard Local API, Vestaboard Cloud API, FiestaBoard Vestaboard]
---

# Split-Flap Boards

:::note Version availability
These instructions describe FiestaBoard v10 (`next` / beta). The output-plugin setup and Divoom Pixoo 64 support are not available in stable v9. Native Apple TV and Android TV apps are coming soon; use a browser for TV viewing.
:::

FiestaBoard drives Vestaboard split-flap boards: the Flagship, the Note, and Note arrays made of several Notes. Every page lands on the board with the same mechanical clatter as anything else you send it.

## Supported Boards

| Board | Grid | Notes |
|---|---|---|
| **Vestaboard Flagship** | 22 columns × 6 rows | Black or white housing. Newer Flagships show a heart where older ones show a degree sign. Pick which one yours has in the board's settings. |
| **Vestaboard Note** | 15 columns × 3 rows | |
| **Note array** | Several Notes tiled into one canvas | See [Note Arrays](/docs/setup/note-arrays) for wiring up each Note. |

FiestaBoard runs on a separate computer, such as a Raspberry Pi or a home server. Nothing gets installed on the board itself.

## Before You Start

You need your board's **API key**. There are two ways to connect, and you choose one when you set the board up:

| Connection | Best for | What you need |
|---|---|---|
| **Local API** (recommended) | Faster updates and transition animations. Works on your home network. | A Local API key and the board's IP address. [How to get them](/docs/setup/api-keys). |
| **Cloud API** | Running FiestaBoard somewhere other than the board's network. No transition animations. | A Read/Write API key from your Vestaboard account. [Cloud API setup](/docs/setup/cloud-api). |

## Set It Up

1. In the setup wizard, pick **Vestaboard**. If FiestaBoard is already set up, open **Displays**, click **Add a display**, and pick **Vestaboard**.
2. In the first-run wizard, choose your connection type and enter your API key, plus the board's IP address for the Local API. Pick your model and housing color, then click **Test connection**.
3. When adding a board from **Displays**, choose its model first, then open the new board's settings to enter its connection details and test it. This path differs from the first-run wizard.

The board now appears in **Displays** and in the board selector. Give it an active page, add it to a schedule, or send it a page from the editor.

## Tips

- **Transitions** need the Local API. Set them in the board's settings on its **Displays** page.
- **Your Vestaboard app keeps working.** FiestaBoard uses the same official API any developer can use. Whatever was sent last wins.
- **Characters the board can't show** are left blank, for example accented letters and curly quotes. The page editor highlights them before you send.

## Troubleshooting

| Symptom | What to check |
|---|---|
| **Test connection** fails on the Local API | The IP address changed. Reserve a fixed address for the board in your router. |
| The board updates, but with no animation | You're on the Cloud API, or the transition is set to None. |
| Pages are cut off | The page was made for a different shape. Pick this board in the page editor's size picker. |

See the general [Troubleshooting](/docs/troubleshooting) guide for more.
