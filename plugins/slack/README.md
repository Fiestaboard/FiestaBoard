# Slack Messages Plugin

![Slack Messages Display](./docs/slack-display.png)

Display recent messages from your Slack channels on your FiestaBoard. Keep track of important conversations and team updates at a glance.

## Features

- **OAuth Authentication**: Secure connection to your Slack workspace via OAuth 2.0
- **Channel Selection**: Choose which channel to monitor
- **Recent Messages**: Display the most recent messages from the selected channel
- **Configurable Display**: Customize the number of messages and whether to show timestamps
- **User Information**: Shows the sender's name for each message
- **Real-time Updates**: Configurable refresh interval (minimum 30 seconds)

## How It Works

The Slack plugin uses OAuth 2.0 to securely connect to your Slack workspace. Once authenticated, it fetches recent messages from a channel you select and displays them on your board. Messages are automatically truncated to fit the board's display constraints.

### OAuth Flow

1. Click "Connect" button in the FiestaBoard integrations page
2. Authorize FiestaBoard to access your Slack workspace
3. Select a channel to monitor
4. Messages will start appearing on your board

## Configuration

### Required Setup

1. **Create a Slack App** at [api.slack.com/apps](https://api.slack.com/apps)
2. **Configure OAuth scopes** (the plugin requires these permissions):
   - `channels:history` - Read messages from public channels
   - `channels:read` - View public channels
   - `groups:history` - Read messages from private channels
   - `groups:read` - View private channels
   - `im:history` - Read direct messages
   - `im:read` - View direct messages
   - `mpim:history` - Read group direct messages
   - `mpim:read` - View group direct messages
   - `users:read` - View user information
3. **Set redirect URI** to `http://your-fiestaboard-url:3000/oauth/callback/slack`
4. **Add environment variables** to your `.env` file:
   ```
   SLACK_CLIENT_ID=your_client_id_here
   SLACK_CLIENT_SECRET=your_client_secret_here
   ```

See [Setup Guide](./docs/SETUP.md) for detailed instructions.

### Plugin Settings

- **Max Messages** (1-20): Maximum number of messages to fetch (default: 5)
- **Show Timestamp**: Display message timestamps (default: enabled)
- **Refresh Interval** (30+ seconds): How often to fetch new messages (default: 60 seconds)

## Template Variables

Use these variables in your page templates:

### Simple Variables

- `{{slack.channel_name}}` - Name of the monitored channel
- `{{slack.message_count}}` - Number of messages fetched
- `{{slack.last_message_text}}` - Text of the most recent message
- `{{slack.last_message_user}}` - User who sent the most recent message
- `{{slack.last_message_time}}` - Timestamp of the most recent message
- `{{slack.status}}` - Status message (e.g., "5 msg")

### Array Variables (for messages list)

- `{{slack.messages.{index}.user}}` - Username of message sender
- `{{slack.messages.{index}.text}}` - Message text
- `{{slack.messages.{index}.time}}` - Message timestamp
- `{{slack.messages.{index}.formatted}}` - Pre-formatted message (user: text)

### Example Template

```
Channel: {{slack.channel_name}}
---
{{slack.messages.0.user}}
{{slack.messages.0.text}}

{{slack.messages.1.user}}
{{slack.messages.1.text}}
```

## API Rate Limits

Slack has rate limits on their API. The plugin respects these limits:

- **Tier 3** methods (conversations.history): 50+ requests per minute
- **Tier 2** methods (users.info): 20+ requests per minute

With the default refresh interval of 60 seconds, the plugin makes approximately:
- 1 request for channel info (once)
- 1 request for messages (every 60 seconds)
- N requests for user info (cached after first fetch)

This is well within Slack's rate limits for normal usage.

## Troubleshooting

### "Not authenticated" error
- Make sure you've completed the OAuth flow by clicking the "Connect" button
- Verify your Slack app credentials are correct in `.env`

### "No channel selected" error
- Select a channel after authenticating
- You can change the channel in the plugin settings

### Messages not updating
- Check the refresh interval setting
- Verify the channel still exists and you have access
- Check FiestaBoard logs for any API errors

### OAuth redirect fails
- Verify the redirect URI in your Slack app matches your FiestaBoard URL
- Make sure the redirect URI includes the port number if using a non-standard port

## Privacy & Security

- **OAuth tokens** are stored securely in FiestaBoard's configuration
- **Messages** are fetched directly from Slack's API and not stored permanently
- **Access** is limited to channels your Slack user can access
- **Tokens** can be revoked at any time from your Slack workspace settings

## Development

### Running Tests

```bash
# Run plugin tests
python scripts/run_plugin_tests.py --plugin=slack

# Run with coverage
python scripts/run_plugin_tests.py --plugin=slack --coverage
```

### Plugin Structure

```
plugins/slack/
├── __init__.py           # Plugin implementation
├── manifest.json         # Plugin metadata and OAuth config
├── README.md            # This file
├── tests/               # Test suite
│   ├── __init__.py
│   └── test_slack.py
└── docs/                # Documentation
    ├── SETUP.md         # Setup instructions
    └── slack-display.png # Screenshot
```

## License

MIT License - see [LICENSE](../../LICENSE) file for details.

## Support

For issues, questions, or contributions, please visit:
- [GitHub Issues](https://github.com/Fiestaboard/FiestaBoard/issues)
- [Plugin Development Guide](../../docs/development/PLUGIN_DEVELOPMENT.md)
