# Dad Jokes Setup

Display random dad jokes on your board using the [icanhazdadjoke](https://icanhazdadjoke.com/) API.

## Overview

**What it does:**
- Fetches a random dad joke from the icanhazdadjoke API
- Displays the joke on your board
- No API key required

**Prerequisites:**
- ✅ Internet connection (to reach icanhazdadjoke.com)
- ✅ No API key needed — the service is free and open

## Quick Setup

### 1. Enable the Plugin

**Option A: Web UI**
1. Go to **Integrations** and find "Dad Jokes"
2. Toggle **Enable Dad Jokes** to on
3. Click **Save Changes**

**Option B: Environment Variable**

Add to your `.env` file:
```bash
DAD_JOKES_ENABLED=true
```

### 2. Use in Templates

Available variables:
- `{{dad_jokes.joke}}` - The full joke text

### 3. Example Template

Create a centered joke display:

```
{center}{{dad_jokes.joke|wrap}}
```

**Tip:** The `|wrap` filter automatically word-wraps long jokes across multiple lines, and `{center}` centers each line on the display.

## Configuration Reference

| Setting | Type | Required | Default | Description |
|---------|------|----------|---------|-------------|
| `enabled` | boolean | No | `false` | Enable or disable dad jokes |

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DAD_JOKES_ENABLED` | No | `false` | Enable dad jokes feature |

## Display Examples

**Short joke:**
```
  I'm afraid for the
  calendar. Its days
     are numbered.
```

**Question and answer:**
```
 Why don't scientists
  trust atoms? Because
   they make up
    everything!
```

## API Information

This plugin uses the [icanhazdadjoke API](https://icanhazdadjoke.com/api):

- **Endpoint:** `GET https://icanhazdadjoke.com/`
- **Authentication:** None required
- **Rate Limits:** No strict rate limit, but please be respectful
- **Format:** JSON with `Accept: application/json` header

### Sample API Response

```json
{
  "id": "R7UfaahVfFd",
  "joke": "My dog used to chase people on a bike a lot. It got so bad I had to take his bike away.",
  "status": 200
}
```

## Troubleshooting

### Joke Not Showing

1. **Check if enabled:**
   ```bash
   grep DAD_JOKES_ENABLED .env
   # Should show: DAD_JOKES_ENABLED=true
   ```

2. **Check logs:**
   ```bash
   docker-compose logs | grep -i "dad joke"
   ```

3. **Check internet connectivity:**
   ```bash
   curl -H "Accept: application/json" https://icanhazdadjoke.com/
   ```

### Plugin Shows "Not Available"

- Ensure the service at https://icanhazdadjoke.com/ is reachable
- Check that your network/firewall allows outbound HTTPS connections

## Restart After Changes

After changing Dad Jokes settings, restart the service:

```bash
docker-compose restart
docker-compose logs -f
```

## Summary

- **Enable jokes**: `DAD_JOKES_ENABLED=true`
- **Use in pages**: Include `{{dad_jokes.joke}}` in your page template
- **No API key needed** — just enable and enjoy!

😄
