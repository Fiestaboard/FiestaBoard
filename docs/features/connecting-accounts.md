---
sidebar_position: 8
description: "Connect a FiestaBoard plugin to an online account such as a music or calendar service, even though your board is only reachable on your home network."
keywords: [FiestaBoard OAuth, connect account, sign in, plugin sign-in, redirect URI, device code, self-hosted OAuth]
---

# Connecting Accounts

Some plugins show data from an account you own on another service: what is playing, your next event, your latest order. Those plugins ask you to **connect** the account once. You sign in on the service's own page; FiestaBoard never sees your password.

A plugin that needs this has an **Account connection** section at the top of its settings.

FiestaBot can sign in to some AI providers the same way, instead of using an API key. That happens in **Settings → AI Providers**; see [AI Providers](/docs/setup/ai-providers#signing-in-instead-of-using-an-api-key). Everything on this page about pasting an address applies there too.

## Connecting

1. Open **Integrations**, find the plugin, and open its settings.
2. Some plugins bring their own app and need nothing else. Others ask for a **client ID** (and sometimes a secret): enter it and press **Save Changes**. The plugin's own setup guide says where to get one. See [Creating your own app](#creating-your-own-app) below.
3. Press **Sign in with** and the service's name, such as **Sign in with Spotify**.

What happens next depends on the plugin.

### Plugins that send you to the service

You are taken to the service to sign in and approve access, then brought back to your board.

On the way back you pass through `fiestaboard.app`. **The first time you connect from a browser, it stops and shows your board's address**, like `http://192.168.1.50:4420`, and asks you to confirm:

- Check that the address is the one you use to open FiestaBoard.
- Leave **Remember this board** ticked so you are not asked again in that browser.
- Press **Continue to my board**.

You land back on Integrations with the plugin connected.

:::info Why the extra stop?
Online services will only send you back to a secure, public web address they were told about in advance. Your board is neither: it lives on your home network. So every FiestaBoard uses the same public return address, and that page hands you on to your own board. It runs entirely in your browser, stores nothing on a server, and will only ever hand a sign-in to an address on a local network. It asks before using an address it has not seen so that a link from someone else cannot quietly send your sign-in to a different machine.
:::

### Plugins that show you a code

Some services let you approve from another device instead. The plugin's settings show a web address and a short code:

1. Open the address on your phone or computer.
2. Enter the code and approve.

The settings update by themselves within a few seconds. If the code expires before you approve it, press **Sign in with** again for a new one. While a code is still showing, **Get a new code** replaces it.

### Plex

**Sign in with Plex** opens Plex's sign-in page in a new tab. Approve FiestaBoard there. The settings say they are waiting and update by themselves when you approve; there is no code to type.

### When the sign-in doesn't come back

Sometimes the browser does not make it back to your board: you approved on a different device, the return page could not reach the board, or the service shows a code instead of sending you back. After you press **Sign in with**, the settings offer **Sign-in didn't come back? Paste the address or code** for ten minutes:

1. Open it.
2. Paste the whole address from the tab where the sign-in stopped, or the code the service showed you.
3. Press **Finish sign-in**.

**Open the sign-in page again** reopens the service's page if you closed it. Some services always end this way; for those the box opens by itself and says what to copy.

Some services also offer **Sign in without a browser redirect**. The service then shows a code, and you paste it into the same box.

## Creating your own app

Only needed for plugins whose settings ask for a client ID. If the settings show just a sign-in button, the plugin brings its own app; skip this section.

Most services require an "app" or "client" registration before they will let anything sign in on your behalf. It is free and takes a few minutes in the service's developer settings. The plugin's setup guide links to the right page.

The plugin's **Account connection** section walks you through it in numbered steps:

1. **Create the app.** The section links to the service's developer page and to the plugin's step-by-step guide.
2. **Give the app the redirect URI** (also called a callback URL). Copy it from the section with the copy button. It looks like this:

   ```text
   https://fiestaboard.app/auth/oauth/redirect
   ```

   Services compare this address exactly, so always copy the one your board shows. FiestaBoard 9.5 through 9.7 show it with `.html` on the end.
3. **Copy the app's client ID into the section.** If the service also gives you a **client secret** and there is a field for it, enter that too. The secret stays on your board.

Then press **Sign in with** and the service's name. It saves what you entered and starts the sign-in.

## Disconnecting

Open the plugin's settings and press **Disconnect**. FiestaBoard deletes the access it was holding. To also remove FiestaBoard from the service's list of connected apps, do that in your account settings on the service.

Uninstalling a plugin disconnects it.

## Where your sign-in is kept

- Access tokens are stored on your board in `data/oauth_tokens.json`, readable only by the FiestaBoard process.
- They are never sent to your browser and are not included in backups, so after restoring a backup onto a new board you connect again.
- Each plugin has its own connection. Two plugins that use the same service do not share access, and neither can see the other's.

## Troubleshooting

**"This sign-in can't be passed on."** You opened your board through a public address. Open it by its local address, such as `http://192.168.1.50:4420` or `http://fiestaboard.local:4420`, and connect from there.

**"That sign-in did not start from this board, or was already used."** The return link was opened twice, or belongs to an earlier attempt. Sign in again.

**"The sign-in took too long."** You have ten minutes from pressing the sign-in button. Press it again.

**"The provider rejected the sign-in."** The client ID or secret does not match the app you created, or the app's redirect URI is not exactly the one your board shows. Fix it and sign in again.

**The service says the redirect URI is invalid or does not match.** The app must list exactly the address shown in the plugin's **Account connection** section. If you set the app up on an older FiestaBoard, add the new address to the app as well.

**The browser shows "can't reach this page" after signing in.** The device you signed in on cannot reach your board at the address shown. Make sure it is on the same network as the board, or copy the page's whole address and paste it into the plugin's settings (see [When the sign-in doesn't come back](#when-the-sign-in-doesnt-come-back)).

**The plugin says "Reconnect needed", or "*Service* stopped accepting the sign-in. Sign in again."** The service stopped accepting the stored access, usually because you removed the app from your account or changed your password. Press **Reconnect**.

**"That doesn't look like a sign-in address or code."** Copy the whole address from the address bar, from `https://` to the end, and paste it again.

**"That address belongs to a different or finished sign-in."** The pasted address is from an earlier attempt, or was already used. Press **Sign in with** again and paste the new address.

**"There is no sign-in waiting for a code."** The ten minutes ran out, or the board restarted. Start the sign-in again.

**The plugin asks for an address, such as Home Assistant's.** Enter it and save before you sign in. It must start with `https://`, or with `http://` only for something on your home network, such as `http://192.168.1.20:8123` or `http://homeassistant.local:8123`.

**The sign-in button is greyed out.** The plugin needs a client ID first. Paste it into the **Account connection** section.

**To use a different app**, press **Disconnect**. The setup steps and the client ID field come back.

**Building a plugin that signs in?** See [Signing In with OAuth](/docs/development/plugin-oauth) in the developer docs.

**To stop a browser passing sign-ins to a board without asking**, open [the list of remembered boards](https://fiestaboard.app/auth/oauth/boards.html) in that browser and press **Forget**.
