# Vestaboard Setup Guide

Connect a Vestaboard Flagship, Note or Note array to FiestaBoard.

## Overview

**What it does:** FiestaBoard shows your pages on your Vestaboard, through the board's Local API on your network or through Vestaboard's cloud.

**Prerequisites:**

- A Vestaboard Flagship, Note or Note array, set up in the Vestaboard app
- For the Local API: the board on the same network as FiestaBoard, and a Local API enablement token from [Vestaboard](https://www.vestaboard.com/local-api)
- For the cloud: a Read/Write API key from [web.vestaboard.com](https://web.vestaboard.com), or a note-array token

## Quick Setup

1. **Enable:** the Vestaboard output ships with FiestaBoard. In the setup wizard, or under **Settings → Boards → Add board**, choose **Vestaboard**.
2. **Configure:** pick **Local API** or **Cloud**.
   - Local API: select **Scan network** to find the board, or type its IP address. Paste your enablement token and select **Enable Local API**; FiestaBoard fills in the key.
   - Cloud: paste your Read/Write API key.
   - Note array: set how many Notes wide and tall it is, then assign each Note its IP address and key, or paste the array's cloud token.
3. **Template:** select **Test connection**, then save. Any page you create fits the board's size.
4. **View:** your active page appears on the board within a refresh.

## Template Variables

| Variable | Description |
|----------|-------------|
| None | An output plugin adds no template variables: it shows what your pages render. |

## Configuration Reference

| Setting | Required | Description |
|---------|----------|-------------|
| Connection (`api_mode`) | Yes | `local` (Local API) or `cloud`. |
| Board IP address (`host`) | Local API | The board's IP address or hostname. |
| Local API port (`port`) | No | Default `7000`. |
| Local API key (`local_api_key`) | Local API | Issued by the board when you enable the Local API. |
| Read/Write API key (`cloud_key`) | Cloud | From Vestaboard's web app. |
| Note array token (`note_array_token`) | Cloud note array | From Vestaboard. |
| Note array tiles (`tiles`) | Local note array | Each Note's position, IP address, port and Local API key. |

Environment variables (developers):

| Variable | Description |
|----------|-------------|
| `VESTABOARD_RW_API_URL` | Overrides the Read/Write Cloud API URL (default `https://rw.vestaboard.com/`). |
| `VESTABOARD_CLOUD_API_URL` | Overrides the note-array Cloud API URL (default `https://cloud.vestaboard.com/`). |
| `FIESTABOARD_OUTPUTS_ALLOW_HOSTS` | When set, FiestaBoard contacts only these hosts. The development stack uses it so a real board is never reached by accident. |

## Troubleshooting

**"Could not connect to the board"**
- Make sure the board is on and on the same network as FiestaBoard.
- Check the IP address on your router's admin page, or select **Scan network**.
- Make sure the Local API is enabled on the board.

**"Your API key was rejected"**
- Local API: re-enable the Local API with a new enablement token; an old key stops working when a new one is issued.
- Cloud: copy the Read/Write API key again from [web.vestaboard.com](https://web.vestaboard.com).

**Messages arrive slowly over the cloud**
- Vestaboard's cloud accepts one message every 15 seconds. FiestaBoard waits that long between messages, and longer if the cloud asks it to. The Local API has no such limit.

**One Note of an array stays blank**
- Check that Note's IP address and key under the array's tiles, and select **Identify** to see which Note is which.
