"""Spotify Now Playing plugin for FiestaBoard.

Displays what's currently playing on Spotify via the Spotify Web API.
Uses OAuth 2.0 with refresh tokens for authentication.
"""

import base64
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# Spotify API endpoints
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_NOW_PLAYING_URL = "https://api.spotify.com/v1/me/player/currently-playing"


class SpotifyPlugin(PluginBase):
    """Spotify Now Playing plugin.

    Fetches the currently playing track from a user's Spotify account
    using the Spotify Web API with OAuth 2.0 refresh token flow.
    """

    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the Spotify plugin."""
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    @property
    def plugin_id(self) -> str:
        """Return plugin identifier."""
        return "spotify"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate Spotify configuration."""
        errors = []

        client_id = config.get("client_id", "").strip()
        if not client_id:
            client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
            if not client_id:
                errors.append("Spotify Client ID is required")

        client_secret = config.get("client_secret", "").strip()
        if not client_secret:
            client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
            if not client_secret:
                errors.append("Spotify Client Secret is required")

        refresh_token = config.get("refresh_token", "").strip()
        if not refresh_token:
            refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN", "").strip()
            if not refresh_token:
                errors.append("Spotify refresh token is required")

        refresh_seconds = config.get("refresh_seconds", 30)
        if not isinstance(refresh_seconds, int) or refresh_seconds < 10:
            errors.append("Refresh interval must be at least 10 seconds")

        return errors

    def _get_client_id(self) -> str:
        """Get client ID from config or environment."""
        return (
            self.config.get("client_id", "").strip()
            or os.getenv("SPOTIFY_CLIENT_ID", "").strip()
        )

    def _get_client_secret(self) -> str:
        """Get client secret from config or environment."""
        return (
            self.config.get("client_secret", "").strip()
            or os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
        )

    def _get_refresh_token(self) -> str:
        """Get refresh token from config or environment."""
        return (
            self.config.get("refresh_token", "").strip()
            or os.getenv("SPOTIFY_REFRESH_TOKEN", "").strip()
        )

    def _refresh_access_token(self) -> Optional[str]:
        """Refresh the OAuth access token using the refresh token.

        Returns:
            Access token string, or None if refresh failed.
        """
        # Check if current token is still valid
        if (
            self._access_token
            and self._token_expiry
            and datetime.now() < self._token_expiry
        ):
            return self._access_token

        client_id = self._get_client_id()
        client_secret = self._get_client_secret()
        refresh_token = self._get_refresh_token()

        if not all([client_id, client_secret, refresh_token]):
            return None

        # Encode credentials for Basic auth
        credentials = f"{client_id}:{client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        try:
            response = requests.post(
                SPOTIFY_TOKEN_URL, headers=headers, data=data, timeout=10
            )

            if response.status_code != 200:
                logger.warning(
                    f"Spotify token refresh failed: {response.status_code}"
                )
                return None

            token_data = response.json()
            self._access_token = token_data.get("access_token")
            # Tokens typically expire in 3600 seconds; use a buffer
            expires_in = token_data.get("expires_in", 3600)
            self._token_expiry = datetime.now() + timedelta(
                seconds=expires_in - 60
            )

            return self._access_token

        except requests.exceptions.RequestException as e:
            logger.warning(f"Error refreshing Spotify token: {e}")
            return None

    def fetch_data(self) -> PluginResult:
        """Fetch currently playing track from Spotify."""
        client_id = self._get_client_id()
        client_secret = self._get_client_secret()
        refresh_token = self._get_refresh_token()

        if not client_id:
            return PluginResult(
                available=False,
                error="Spotify Client ID not configured",
            )

        if not client_secret:
            return PluginResult(
                available=False,
                error="Spotify Client Secret not configured",
            )

        if not refresh_token:
            return PluginResult(
                available=False,
                error="Spotify refresh token not configured",
            )

        # Check cache
        refresh_seconds = self.config.get("refresh_seconds", 30)
        if self._cache and self._cache_time:
            cache_age = (datetime.now() - self._cache_time).total_seconds()
            if cache_age < refresh_seconds:
                logger.debug(f"Using cached data (age: {cache_age:.0f}s)")
                return PluginResult(available=True, data=self._cache)

        # Get access token
        access_token = self._refresh_access_token()
        if not access_token:
            if self._cache:
                return PluginResult(available=True, data=self._cache)
            return PluginResult(
                available=False,
                error="Failed to obtain Spotify access token",
            )

        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(
                SPOTIFY_NOW_PLAYING_URL, headers=headers, timeout=10
            )

            # 204 = nothing currently playing
            if response.status_code == 204:
                result_data = self._empty_data("Nothing playing")
                self._cache = result_data
                self._cache_time = datetime.now()
                return PluginResult(available=True, data=result_data)

            if response.status_code == 401:
                # Token expired, clear it and retry once
                self._access_token = None
                self._token_expiry = None
                if self._cache:
                    return PluginResult(available=True, data=self._cache)
                return PluginResult(
                    available=False,
                    error="Spotify authentication failed",
                )

            if response.status_code == 403:
                return PluginResult(
                    available=False,
                    error="Spotify access forbidden - check app permissions",
                )

            if response.status_code != 200:
                return PluginResult(
                    available=False,
                    error=f"Spotify API error: {response.status_code}",
                )

            data = response.json()

            # Check if it's a track (not podcast/episode)
            currently_playing_type = data.get("currently_playing_type", "track")
            is_playing = data.get("is_playing", False)

            item = data.get("item")
            if not item:
                result_data = self._empty_data("Nothing playing")
                self._cache = result_data
                self._cache_time = datetime.now()
                return PluginResult(available=True, data=result_data)

            # Extract track info
            title = item.get("name", "Unknown")

            # Artists is a list of artist objects
            artists = item.get("artists", [])
            if artists:
                artist_name = artists[0].get("name", "Unknown")
            else:
                artist_name = "Unknown"

            # Album info
            album_info = item.get("album", {})
            album_name = album_info.get("name", "")

            # Get artwork URL (largest available)
            images = album_info.get("images", [])
            artwork_url = ""
            if images:
                # Images are sorted by size (largest first)
                artwork_url = images[0].get("url", "")

            # Track URL
            external_urls = item.get("external_urls", {})
            track_url = external_urls.get("spotify", "")

            # Build formatted string
            show_album = self.config.get("show_album", False)
            if show_album and album_name:
                formatted = f"{title} - {artist_name}"
            else:
                formatted = f"{title} by {artist_name}"

            # Status text
            if is_playing:
                status = "NOW PLAYING"
            else:
                status = "PAUSED"

            result_data = {
                "title": title,
                "artist": artist_name,
                "album": album_name,
                "is_playing": is_playing,
                "artwork_url": artwork_url,
                "track_url": track_url,
                "formatted": formatted,
                "status": status,
            }

            # Update cache
            self._cache = result_data
            self._cache_time = datetime.now()

            return PluginResult(available=True, data=result_data)

        except requests.exceptions.Timeout:
            logger.warning("Spotify API request timed out")
            if self._cache:
                return PluginResult(available=True, data=self._cache)
            return PluginResult(
                available=False,
                error="Request timed out",
            )
        except requests.exceptions.RequestException as e:
            logger.exception("Error fetching Spotify data")
            if self._cache:
                return PluginResult(available=True, data=self._cache)
            return PluginResult(
                available=False,
                error=f"Network error: {str(e)}",
            )
        except Exception as e:
            logger.exception("Unexpected error fetching Spotify data")
            if self._cache:
                return PluginResult(available=True, data=self._cache)
            return PluginResult(
                available=False,
                error=str(e),
            )

    def _empty_data(self, status: str = "Nothing playing") -> Dict[str, Any]:
        """Return empty data structure when no track is available."""
        return {
            "title": "",
            "artist": "",
            "album": "",
            "is_playing": False,
            "artwork_url": "",
            "track_url": "",
            "formatted": "",
            "status": status,
        }

    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted display for the board."""
        if not self._cache:
            result = self.fetch_data()
            if not result.available:
                return None

        data = self._cache
        if not data or not data.get("title"):
            return None

        lines = []

        # Status line
        status = data.get("status", "NOW PLAYING")
        lines.append(status.center(22))

        # Empty line
        lines.append("")

        # Title (may need to truncate)
        title = data.get("title", "")[:22]
        lines.append(title.center(22))

        # Artist
        artist = data.get("artist", "")[:22]
        lines.append(artist.center(22))

        # Album (if configured and available)
        album = data.get("album", "")
        if self.config.get("show_album", False) and album:
            lines.append(album[:22].center(22))
        else:
            lines.append("")

        # Pad to 6 lines
        while len(lines) < 6:
            lines.append("")

        return lines[:6]

    def cleanup(self) -> None:
        """Cleanup when plugin is disabled."""
        self._cache = None
        self._cache_time = None
        self._access_token = None
        self._token_expiry = None
        logger.info(f"Plugin {self.plugin_id} cleanup")


# Export the plugin class
Plugin = SpotifyPlugin
