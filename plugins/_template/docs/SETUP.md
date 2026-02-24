# [Plugin Name] Setup Guide

> This is a template for plugin setup documentation. Replace the content below with your plugin's setup instructions.

## Overview

**What it does:**
- Feature 1
- Feature 2
- Feature 3

**Prerequisites:**
- ✅ API key from [service] (required/optional)
- ✅ Account at [service]
- ✅ Other requirements

## Quick Setup

### 1. Get Your API Key

1. Go to [service website](https://example.com)
2. Create an account
3. Navigate to API settings
4. Copy your API key

### 2. Configure the Plugin

In the FiestaBoard web UI:
1. Go to **Integrations** and enable the plugin
2. Click **Configure**
3. Enter your API key
4. Configure other settings as needed
5. Click **Save Changes**

### 3. Use in Templates

Available variables:
- `{plugin_name.variable1}` - Description
- `{plugin_name.variable2}` - Description

Example template:
```
{plugin_name.variable1} - {plugin_name.variable2}
```

## Configuration Reference

| Setting | Type | Required | Description |
|---------|------|----------|-------------|
| `api_key` | string | Yes | Your API key from [service] |
| `option1` | string | No | Description of option |
| `option2` | boolean | No | Description of option |

## Troubleshooting

### Common Issues

**Issue: Plugin shows "Not Available"**
- Ensure your API key is correct
- Check that the service is accessible
- Verify your account has API access

**Issue: Data not updating**
- Check the refresh interval setting
- Verify the API isn't rate limited

## API Limits

| Plan | Requests | Notes |
|------|----------|-------|
| Free | X/month | Suitable for basic use |
| Paid | Unlimited | For frequent updates |

## Screenshots

<!-- Add screenshots of your plugin in action -->
<!-- Place images in this docs/ directory and reference them: -->
<!-- ![Description](./screenshot.png) -->

## Support

- Plugin Repository: [GitHub URL]
- Issues: [GitHub Issues URL]
- Author: [Your Name]

