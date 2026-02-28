# OAuth Integration System

FiestaBoard includes a secure OAuth 2.0 integration system for services like Spotify, Google Calendar, and other third-party APIs that require user authorization.

## Overview

The OAuth system provides:
- **Encrypted token storage** - All OAuth tokens are encrypted at rest using Fernet symmetric encryption
- **Automatic token refresh** - Access tokens are automatically refreshed when they expire
- **Multi-board support** - Each board can have separate OAuth connections
- **Extensible architecture** - Easy to add new OAuth providers
- **Backward compatibility** - Supports both OAuth flow and manual token configuration

## Architecture

### Components

1. **SecretsManager** (`src/security/secrets_manager.py`)
   - Encrypts and stores sensitive credentials
   - Uses Fernet encryption with a master key from `FIESTABOARD_MASTER_KEY` environment variable
   - Stores encrypted data in `/app/data/secrets.enc`

2. **OAuthProvider** (`src/security/oauth_providers.py`)
   - Base class for all OAuth integrations
   - Handles authorization URLs, token exchange, and token refresh
   - Built-in providers: Spotify (more coming soon)

3. **OAuth API Endpoints** (`src/api_server.py`)
   - `GET /api/oauth/{provider}/authorize` - Start OAuth flow
   - `GET /api/oauth/{provider}/callback` - Handle OAuth callback
   - `GET /api/oauth/{provider}/status` - Check connection status
   - `DELETE /api/oauth/{provider}` - Disconnect and clear tokens
   - `GET /api/oauth/providers` - List available providers

4. **OAuth UI Component** (`web/src/components/oauth-connect-button.tsx`)
   - React component for connecting/disconnecting OAuth providers
   - Shows connection status and token validity
   - Handles redirect flows

## Setup

### Environment Variables

#### Production Setup (Recommended)

Set the master encryption key in your environment:

```bash
# Generate a secure random key
export FIESTABOARD_MASTER_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

**IMPORTANT:** Store this key securely! If you lose it, all encrypted tokens will be unrecoverable.

For Docker deployments, add to your `.env` file or `docker-compose.yml`:

```yaml
environment:
  - FIESTABOARD_MASTER_KEY=your-secure-key-here
```

#### Quick Start / Development (Optional)

**No master key required!** If you don't set `FIESTABOARD_MASTER_KEY`:
- ✅ OAuth system works immediately - no setup needed
- ✅ Great for testing and demos
- ⚠️ Tokens don't persist across restarts - you'll need to reconnect OAuth after restarting FiestaBoard
- 📝 System logs a warning on startup

**When to set the master key:**
- You're deploying to production
- You want OAuth connections to survive restarts
- You're migrating to a new server (same key = same tokens)

**When you don't need it:**
- Quick testing or demo
- Development environment with frequent rebuilds
- You're okay reconnecting OAuth occasionally

## Adding a New OAuth Provider

### 1. Create the OAuth Provider Class

Create a new provider in `src/security/oauth_providers.py`:

```python
class GoogleCalendarOAuthProvider(OAuthProvider):
    @property
    def provider_id(self) -> str:
        return "google_calendar"
    
    @property
    def provider_name(self) -> str:
        return "Google Calendar"
    
    def get_config(self, board_id: str) -> Optional[OAuthConfig]:
        # Get OAuth configuration from plugin or settings
        return OAuthConfig(
            client_id="...",
            client_secret="...",
            redirect_uri="http://localhost:8080/api/oauth/google_calendar/callback",
            scope="https://www.googleapis.com/auth/calendar.readonly",
            authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
            token_endpoint="https://oauth2.googleapis.com/token"
        )
    
    def get_authorization_url(self, board_id: str, state: str) -> str:
        config = self.get_config(board_id)
        if not config:
            raise ValueError("OAuth not configured")
        
        params = {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": config.redirect_uri,
            "scope": config.scope,
            "state": state,
            "access_type": "offline",  # Google-specific: get refresh token
            "prompt": "consent"  # Google-specific: force consent screen
        }
        
        return f"{config.authorization_endpoint}?{urlencode(params)}"
    
    def exchange_code_for_tokens(self, board_id: str, code: str) -> OAuthTokens:
        config = self.get_config(board_id)
        if not config:
            raise ValueError("OAuth not configured")
        
        response = requests.post(
            config.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.redirect_uri,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
            },
            timeout=10
        )
        
        if response.status_code != 200:
            raise ValueError(f"Token exchange failed: {response.status_code}")
        
        data = response.json()
        
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope"),
        )
    
    def refresh_access_token(self, board_id: str) -> Optional[OAuthTokens]:
        config = self.get_config(board_id)
        if not config:
            return None
        
        refresh_token = self.get_refresh_token(board_id)
        if not refresh_token:
            return None
        
        response = requests.post(
            config.token_endpoint,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
            },
            timeout=10
        )
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=data.get("expires_in"),
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope"),
        )

# Register the provider
register_oauth_provider(GoogleCalendarOAuthProvider())
```

### 2. Update Plugin to Use OAuth

In your plugin's `__init__.py`:

```python
def _get_access_token(self) -> Optional[str]:
    """Get access token from OAuth provider."""
    try:
        from src.security.oauth_providers import get_oauth_provider
        
        provider = get_oauth_provider("google_calendar")
        if not provider:
            return None
        
        board_id = "default"  # TODO: Multi-board support
        
        # OAuth provider handles token refresh automatically
        return provider.get_access_token(board_id)
    
    except Exception as e:
        logger.error(f"OAuth provider not available: {e}")
        return None

def fetch_data(self) -> PluginResult:
    # Get access token
    access_token = self._get_access_token()
    if not access_token:
        return PluginResult(
            available=False,
            error="Not connected to Google Calendar"
        )
    
    # Use token to make API request
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get("https://www.googleapis.com/calendar/v3/events", headers=headers)
    # ...
```

### 3. Add OAuth Field to Manifest

Update your plugin's `manifest.json`:

```json
{
  "id": "google_calendar",
  "name": "Google Calendar",
  "oauth_provider": "google_calendar",
  "settings_schema": {
    "type": "object",
    "properties": {
      "enabled": {
        "type": "boolean",
        "title": "Enabled",
        "default": false
      }
    }
  }
}
```

### 4. Add OAuth Button to UI

The OAuth connect button will automatically appear for plugins with the `oauth_provider` field in their manifest.

## User Flow

1. User opens plugin settings in the UI
2. User sees "Connect to [Provider]" button
3. User clicks button → redirected to provider's authorization page
4. User authorizes the app
5. User is redirected back to FiestaBoard
6. OAuth system exchanges authorization code for access/refresh tokens
7. Tokens are encrypted and stored
8. Plugin can now access the provider's API

## Security

### Encryption

- All tokens are encrypted using Fernet (symmetric encryption)
- Master key is derived from `FIESTABOARD_MASTER_KEY` using PBKDF2
- 100,000 iterations of PBKDF2-SHA256 for key derivation
- Encrypted data is stored in `/app/data/secrets.enc`

### Token Storage

Tokens are stored in this namespace format:

```
{provider_id}:{board_id}
  ├─ access_token (encrypted)
  ├─ refresh_token (encrypted)
  ├─ expires_at (encrypted)
  └─ scope (encrypted)
```

### Token Refresh

- Access tokens are automatically refreshed 5 minutes before expiration
- If refresh fails, the OAuth provider returns `None` and the plugin should handle gracefully
- Users can reconnect via the UI if tokens become invalid

## Migration from Manual Tokens

Plugins can support both OAuth and manual token configuration:

```python
def _get_access_token(self) -> Optional[str]:
    # Try OAuth first
    oauth_token = self._get_access_token_oauth()
    if oauth_token:
        return oauth_token
    
    # Fall back to manual configuration
    return self._get_access_token_manual()
```

This allows gradual migration without breaking existing setups.

## Troubleshooting

### "No master key found" Warning

Set the `FIESTABOARD_MASTER_KEY` environment variable.

### "Failed to decrypt secrets file"

The master key has changed. Either:
1. Restore the original master key
2. Disconnect and reconnect OAuth providers (old tokens will be lost)

### "OAuth provider not found"

The provider hasn't been registered. Check that `register_oauth_provider()` is called in `src/security/oauth_providers.py`.

### Tokens Not Persisting

Check that `/app/data` is mounted as a persistent volume in Docker.

## Future Improvements

- State validation with Redis/database
- PKCE (Proof Key for Code Exchange) for added security
- Refresh token rotation
- Token revocation on disconnect
- Admin UI for managing OAuth applications
- Support for OAuth 1.0a (Twitter, etc.)
