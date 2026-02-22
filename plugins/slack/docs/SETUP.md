# Slack Plugin Setup Guide

This guide walks you through setting up the Slack integration for FiestaBoard.

## Prerequisites

- A Slack workspace where you have permission to install apps
- FiestaBoard installed and running
- Admin access to create a Slack app (or access to an existing app)

## Step 1: Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"**
3. Select **"From scratch"**
4. Enter an app name (e.g., "FiestaBoard")
5. Select your workspace
6. Click **"Create App"**

![Create Slack App](./slack-create-app.png)

## Step 2: Configure OAuth Scopes

1. In your app settings, go to **"OAuth & Permissions"** in the left sidebar
2. Scroll down to **"Scopes"** section
3. Under **"Bot Token Scopes"**, add the following scopes:
   - `channels:history` - Read messages from public channels
   - `channels:read` - View basic channel information
   - `groups:history` - Read messages from private channels
   - `groups:read` - View basic private channel information
   - `im:history` - Read direct messages
   - `im:read` - View direct message information
   - `mpim:history` - Read group direct messages
   - `mpim:read` - View group direct message information
   - `users:read` - View user profile information

![OAuth Scopes](./slack-scopes.png)

## Step 3: Set Redirect URI

1. Still in **"OAuth & Permissions"** page
2. Scroll up to **"Redirect URLs"** section
3. Click **"Add New Redirect URL"**
4. Enter your FiestaBoard URL with the OAuth callback path:
   ```
   http://localhost:3000/oauth/callback/slack
   ```
   
   **Note:** Replace `localhost:3000` with your actual FiestaBoard URL and port. For example:
   - Local development: `http://localhost:3000/oauth/callback/slack`
   - Production: `https://fiestaboard.yourdomain.com/oauth/callback/slack`
   - Custom port: `http://192.168.1.100:4420/oauth/callback/slack`

5. Click **"Add"**
6. Click **"Save URLs"**

![Redirect URI](./slack-redirect-uri.png)

## Step 4: Get Client Credentials

1. Go to **"Basic Information"** in the left sidebar
2. Scroll down to **"App Credentials"** section
3. You'll see:
   - **Client ID** - Copy this value
   - **Client Secret** - Click "Show" and copy this value

![App Credentials](./slack-credentials.png)

⚠️ **Important:** Keep your Client Secret secure! Don't share it or commit it to version control.

## Step 5: Configure FiestaBoard

1. Open your FiestaBoard `.env` file
2. Add the following environment variables:
   ```env
   SLACK_CLIENT_ID=your_client_id_here
   SLACK_CLIENT_SECRET=your_client_secret_here
   ```
3. Replace `your_client_id_here` and `your_client_secret_here` with the values from Step 4
4. Save the file
5. Restart FiestaBoard for the changes to take effect:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

## Step 6: Enable and Authenticate

1. Open FiestaBoard web UI (usually `http://localhost:4420` or `http://localhost:3000` for dev)
2. Navigate to **Integrations** page
3. Find **Slack Messages** plugin
4. Toggle it **ON** to enable
5. Click the **"Connect"** button
6. You'll be redirected to Slack to authorize the app
7. Click **"Allow"** to grant permissions
8. You'll be redirected back to FiestaBoard
9. Select a channel from the dropdown
10. Click **"Select Channel"**

![OAuth Flow](./slack-oauth-flow.png)

## Step 7: Configure Plugin Settings

1. In the Integrations page, click **"Configure"** on the Slack plugin
2. Adjust settings as needed:
   - **Max Messages**: How many recent messages to fetch (1-20)
   - **Show Timestamp**: Whether to display message timestamps
   - **Refresh Interval**: How often to fetch new messages (minimum 30 seconds)
3. Click **"Save Changes"**

## Step 8: Add to a Page

1. Navigate to **Pages** in FiestaBoard
2. Create a new page or edit an existing one
3. Use Slack template variables in your page content:
   ```
   #{{slack.channel_name}}
   
   {{slack.messages.0.user}}:
   {{slack.messages.0.text}}
   
   {{slack.messages.1.user}}:
   {{slack.messages.1.text}}
   ```
4. Save the page and select it as active

Your Slack messages will now appear on your board!

## Troubleshooting

### "OAuth error: invalid_redirect_uri"

**Problem:** The redirect URI doesn't match what's configured in your Slack app.

**Solution:**
1. Check your Slack app's redirect URIs match exactly (including http/https, port, path)
2. Make sure there are no trailing slashes
3. Verify you're using the correct URL (localhost vs IP vs domain)

### "SLACK_CLIENT_ID not configured"

**Problem:** Environment variables aren't loaded.

**Solution:**
1. Verify `.env` file has the correct variable names (no typos)
2. Restart FiestaBoard after adding environment variables
3. Check Docker logs: `docker-compose logs fiestaboard-api`

### "Not authenticated" error

**Problem:** OAuth flow wasn't completed or token expired.

**Solution:**
1. Click the "Connect" button again to re-authenticate
2. Make sure you clicked "Allow" on the Slack authorization page
3. Check that your Slack app is installed in your workspace

### Messages not showing

**Problem:** Plugin is enabled but no messages appear.

**Solution:**
1. Verify you selected a channel after authenticating
2. Check that the channel has recent messages
3. Verify your bot has access to the channel (add it if needed: `/invite @FiestaBoard`)
4. Check refresh interval - first fetch may take up to 60 seconds

### "channel_not_found" error

**Problem:** The selected channel no longer exists or bot lost access.

**Solution:**
1. Go to plugin settings and select a different channel
2. In Slack, add the bot to the channel: `/invite @FiestaBoard`
3. Verify the channel still exists

## Advanced Configuration

### Multiple Workspaces

To monitor multiple Slack workspaces, you'll need to:
1. Create separate Slack apps for each workspace
2. Use different plugin instances (not currently supported - feature request!)

### Private Channels

To access private channels:
1. The OAuth scopes include `groups:history` and `groups:read` for private channel access
2. Invite the bot to the private channel: `/invite @FiestaBoard`
3. The channel will appear in the channel selector after authentication

### Custom Refresh Interval

To reduce API calls or get faster updates:
1. Open plugin settings
2. Adjust "Refresh Interval" (minimum 30 seconds)
3. Note: More frequent updates = more API calls = higher rate limit usage

## Security Best Practices

1. **Keep credentials secure**: Never commit `.env` file to version control
2. **Use HTTPS in production**: Especially important for OAuth redirects
3. **Rotate secrets regularly**: Generate new client secret periodically
4. **Limit channel access**: Only add bot to channels you want to monitor
5. **Monitor workspace apps**: Regularly review installed apps in Slack settings

## Need Help?

- **Plugin Issues**: [GitHub Issues](https://github.com/Fiestaboard/FiestaBoard/issues)
- **Slack API Docs**: [Slack API Documentation](https://api.slack.com/docs)
- **OAuth Guide**: [Slack OAuth Documentation](https://api.slack.com/authentication/oauth-v2)
- **FiestaBoard Docs**: [Plugin Development Guide](../../../docs/development/PLUGIN_DEVELOPMENT.md)
