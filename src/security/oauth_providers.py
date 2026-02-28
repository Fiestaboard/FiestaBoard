"""OAuth provider infrastructure for FiestaBoard.

Provides a registry and base classes for OAuth 2.0 integrations.
Each provider (Spotify, Google Calendar, etc.) implements the OAuthProvider interface.
"""

import logging
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, Any
from urllib.parse import urlencode

import requests

from .secrets_manager import get_secrets_manager

logger = logging.getLogger(__name__)


@dataclass
class OAuthConfig:
    """OAuth configuration for a provider."""
    client_id: str
    client_secret: str
    redirect_uri: str
    scope: str
    authorization_endpoint: str
    token_endpoint: str


@dataclass
class OAuthTokens:
    """OAuth tokens returned by a provider."""
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None  # seconds
    token_type: str = "Bearer"
    scope: Optional[str] = None
    expires_at: Optional[float] = None  # Unix timestamp


class OAuthProvider(ABC):
    """Base class for OAuth providers."""
    
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g., 'spotify', 'google_calendar')."""
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name for this provider (e.g., 'Spotify', 'Google Calendar')."""
        pass
    
    @abstractmethod
    def get_config(self, board_id: str) -> Optional[OAuthConfig]:
        """Get OAuth configuration for this provider and board.
        
        Args:
            board_id: Board identifier
            
        Returns:
            OAuthConfig if configured, None otherwise
        """
        pass
    
    @abstractmethod
    def get_authorization_url(self, board_id: str, state: str) -> str:
        """Get the authorization URL for the OAuth flow.
        
        Args:
            board_id: Board identifier
            state: CSRF state token
            
        Returns:
            Authorization URL to redirect user to
        """
        pass
    
    @abstractmethod
    def exchange_code_for_tokens(self, board_id: str, code: str) -> OAuthTokens:
        """Exchange authorization code for access/refresh tokens.
        
        Args:
            board_id: Board identifier
            code: Authorization code from OAuth callback
            
        Returns:
            OAuthTokens containing access token and refresh token
            
        Raises:
            ValueError: If exchange fails
        """
        pass
    
    @abstractmethod
    def refresh_access_token(self, board_id: str) -> Optional[OAuthTokens]:
        """Refresh the access token using the refresh token.
        
        Args:
            board_id: Board identifier
            
        Returns:
            New OAuthTokens, or None if refresh fails
        """
        pass
    
    def get_access_token(self, board_id: str) -> Optional[str]:
        """Get a valid access token, refreshing if necessary.
        
        Args:
            board_id: Board identifier
            
        Returns:
            Valid access token, or None if not available
        """
        secrets = get_secrets_manager()
        namespace = f"{self.provider_id}:{board_id}"
        
        # Check if we have a token
        access_token = secrets.get_secret(namespace, "access_token")
        if not access_token:
            return None
        
        # Check if token is expired
        expires_at_str = secrets.get_secret(namespace, "expires_at")
        if expires_at_str:
            try:
                expires_at = float(expires_at_str)
                # Refresh if token expires in less than 5 minutes
                if time.time() >= (expires_at - 300):
                    logger.debug(f"Access token for {self.provider_id}:{board_id} is expired, refreshing")
                    tokens = self.refresh_access_token(board_id)
                    if tokens:
                        self.store_tokens(board_id, tokens)
                        return tokens.access_token
                    else:
                        logger.warning(f"Failed to refresh access token for {self.provider_id}:{board_id}")
                        return None
            except (ValueError, TypeError):
                logger.warning(f"Invalid expires_at value for {self.provider_id}:{board_id}")
        
        return access_token
    
    def store_tokens(self, board_id: str, tokens: OAuthTokens):
        """Store OAuth tokens securely.
        
        Args:
            board_id: Board identifier
            tokens: Tokens to store
        """
        secrets = get_secrets_manager()
        namespace = f"{self.provider_id}:{board_id}"
        
        secrets.set_secret(namespace, "access_token", tokens.access_token)
        
        if tokens.refresh_token:
            secrets.set_secret(namespace, "refresh_token", tokens.refresh_token)
        
        if tokens.expires_in:
            # Calculate expiration timestamp
            expires_at = time.time() + tokens.expires_in
            secrets.set_secret(namespace, "expires_at", str(expires_at))
        
        if tokens.scope:
            secrets.set_secret(namespace, "scope", tokens.scope)
        
        logger.info(f"Stored OAuth tokens for {self.provider_id}:{board_id}")
    
    def get_refresh_token(self, board_id: str) -> Optional[str]:
        """Get the stored refresh token.
        
        Args:
            board_id: Board identifier
            
        Returns:
            Refresh token, or None if not available
        """
        secrets = get_secrets_manager()
        namespace = f"{self.provider_id}:{board_id}"
        return secrets.get_secret(namespace, "refresh_token")
    
    def clear_tokens(self, board_id: str):
        """Clear all stored tokens for a board.
        
        Args:
            board_id: Board identifier
        """
        secrets = get_secrets_manager()
        namespace = f"{self.provider_id}:{board_id}"
        secrets.delete_secret(namespace)
        logger.info(f"Cleared OAuth tokens for {self.provider_id}:{board_id}")


class SpotifyOAuthProvider(OAuthProvider):
    """Spotify OAuth 2.0 provider."""
    
    @property
    def provider_id(self) -> str:
        return "spotify"
    
    @property
    def provider_name(self) -> str:
        return "Spotify"
    
    def get_config(self, board_id: str) -> Optional[OAuthConfig]:
        """Get Spotify OAuth configuration.
        
        For now, reads from plugin config. In the future, this could come from
        a centralized OAuth settings table.
        """
        from ..config_manager import get_config_manager
        
        config_mgr = get_config_manager()
        config = config_mgr.get_config()
        
        # Get Spotify plugin config
        plugins = config.get("plugins", {})
        spotify_config = plugins.get("spotify", {})
        
        client_id = spotify_config.get("client_id", "").strip()
        client_secret = spotify_config.get("client_secret", "").strip()
        
        if not client_id or not client_secret:
            return None
        
        # Build redirect URI (assumes API server is accessible at this URL)
        # TODO: Make this configurable
        redirect_uri = "http://localhost:8080/api/oauth/spotify/callback"
        
        return OAuthConfig(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-read-currently-playing",
            authorization_endpoint="https://accounts.spotify.com/authorize",
            token_endpoint="https://accounts.spotify.com/api/token"
        )
    
    def get_authorization_url(self, board_id: str, state: str) -> str:
        """Get Spotify authorization URL."""
        config = self.get_config(board_id)
        if not config:
            raise ValueError("Spotify OAuth not configured")
        
        params = {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": config.redirect_uri,
            "scope": config.scope,
            "state": state,
        }
        
        return f"{config.authorization_endpoint}?{urlencode(params)}"
    
    def exchange_code_for_tokens(self, board_id: str, code: str) -> OAuthTokens:
        """Exchange authorization code for Spotify tokens."""
        config = self.get_config(board_id)
        if not config:
            raise ValueError("Spotify OAuth not configured")
        
        try:
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
                logger.error(f"Spotify token exchange failed: {response.status_code} {response.text}")
                raise ValueError(f"Token exchange failed: {response.status_code}")
            
            data = response.json()
            
            return OAuthTokens(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                expires_in=data.get("expires_in"),
                token_type=data.get("token_type", "Bearer"),
                scope=data.get("scope"),
            )
        
        except requests.RequestException as e:
            logger.error(f"Spotify token exchange request failed: {e}")
            raise ValueError(f"Token exchange failed: {e}")
    
    def refresh_access_token(self, board_id: str) -> Optional[OAuthTokens]:
        """Refresh Spotify access token."""
        config = self.get_config(board_id)
        if not config:
            logger.error("Spotify OAuth not configured")
            return None
        
        refresh_token = self.get_refresh_token(board_id)
        if not refresh_token:
            logger.error(f"No refresh token found for Spotify:{board_id}")
            return None
        
        try:
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
                logger.error(f"Spotify token refresh failed: {response.status_code} {response.text}")
                return None
            
            data = response.json()
            
            return OAuthTokens(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", refresh_token),  # Reuse old if not provided
                expires_in=data.get("expires_in"),
                token_type=data.get("token_type", "Bearer"),
                scope=data.get("scope"),
            )
        
        except requests.RequestException as e:
            logger.error(f"Spotify token refresh request failed: {e}")
            return None


# OAuth Provider Registry
_PROVIDERS: Dict[str, OAuthProvider] = {}


def register_oauth_provider(provider: OAuthProvider):
    """Register an OAuth provider.
    
    Args:
        provider: OAuthProvider instance to register
    """
    _PROVIDERS[provider.provider_id] = provider
    logger.info(f"Registered OAuth provider: {provider.provider_name} ({provider.provider_id})")


def get_oauth_provider(provider_id: str) -> Optional[OAuthProvider]:
    """Get an OAuth provider by ID.
    
    Args:
        provider_id: Provider identifier (e.g., 'spotify')
        
    Returns:
        OAuthProvider instance, or None if not found
    """
    return _PROVIDERS.get(provider_id)


def list_oauth_providers() -> list[str]:
    """List all registered OAuth providers.
    
    Returns:
        List of provider IDs
    """
    return list(_PROVIDERS.keys())


# Register built-in providers
register_oauth_provider(SpotifyOAuthProvider())
