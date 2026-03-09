"""Last.fm Now Playing plugin for FiestaBoard.

Displays what's currently playing via Last.fm scrobbling.
Works with Apple Music, Spotify, and any music source that scrobbles to Last.fm.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# Last.fm API endpoint
LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"


class LastFmPlugin(PluginBase):
    """Last.fm Now Playing plugin.
    
    Fetches the currently playing or most recently played track
    from a user's Last.fm scrobbling history.
    """
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the Last.fm plugin."""
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
    
    @property
    def plugin_id(self) -> str:
        return "last_fm"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate Last.fm configuration."""
        errors = []
        
        username = config.get("username", "").strip()
        if not username:
            # Check environment variable
            username = os.getenv("LASTFM_USERNAME", "").strip()
            if not username:
                errors.append("Last.fm username is required")
        
        api_key = config.get("api_key", "").strip()
        if not api_key:
            # Check environment variable
            api_key = os.getenv("LASTFM_API_KEY", "").strip()
            if not api_key:
                errors.append("Last.fm API key is required")
        
        refresh_seconds = config.get("refresh_seconds", 30)
        if not isinstance(refresh_seconds, int) or refresh_seconds < 10:
            errors.append("Refresh interval must be at least 10 seconds")
        
        return errors
    
    def _get_username(self) -> str:
        """Get username from config or environment."""
        return (
            self.config.get("username", "").strip() 
            or os.getenv("LASTFM_USERNAME", "").strip()
        )
    
    def _get_api_key(self) -> str:
        """Get API key from config or environment."""
        return (
            self.config.get("api_key", "").strip() 
            or os.getenv("LASTFM_API_KEY", "").strip()
        )
    
    def fetch_data(self) -> PluginResult:
        """Fetch currently playing or recent track from Last.fm."""
        username = self._get_username()
        api_key = self._get_api_key()
        
        if not username:
            return PluginResult(
                available=False,
                error="Last.fm username not configured"
            )
        
        if not api_key:
            return PluginResult(
                available=False,
                error="Last.fm API key not configured"
            )
        
        # Check cache
        refresh_seconds = self.config.get("refresh_seconds", 30)
        if self._cache and self._cache_time:
            cache_age = (datetime.now() - self._cache_time).total_seconds()
            if cache_age < refresh_seconds:
                logger.debug(f"Using cached data (age: {cache_age:.0f}s)")
                return PluginResult(available=True, data=self._cache)
        
        try:
            # Call Last.fm API
            params = {
                "method": "user.getRecentTracks",
                "user": username,
                "api_key": api_key,
                "format": "json",
                "limit": 1,
            }
            
            response = requests.get(LASTFM_API_URL, params=params, timeout=10)
            
            if response.status_code == 403:
                return PluginResult(
                    available=False,
                    error="Invalid API key"
                )
            
            if response.status_code == 404:
                return PluginResult(
                    available=False,
                    error=f"User '{username}' not found"
                )
            
            if response.status_code != 200:
                return PluginResult(
                    available=False,
                    error=f"Last.fm API error: {response.status_code}"
                )
            
            data = response.json()
            
            # Check for API error response
            if "error" in data:
                error_msg = data.get("message", "Unknown error")
                return PluginResult(
                    available=False,
                    error=f"Last.fm error: {error_msg}"
                )
            
            # Parse response
            tracks = data.get("recenttracks", {}).get("track", [])
            
            if not tracks:
                return PluginResult(
                    available=True,
                    data=self._empty_data("No recent tracks")
                )
            
            # Handle case where tracks is a single dict instead of list
            if isinstance(tracks, dict):
                tracks = [tracks]
            
            track = tracks[0]
            
            # Check if currently playing (nowplaying attribute)
            is_playing = track.get("@attr", {}).get("nowplaying") == "true"
            
            # Extract track info
            title = track.get("name", "Unknown")
            artist = track.get("artist", {})
            # Artist can be a dict or a string depending on API response
            if isinstance(artist, dict):
                artist_name = artist.get("#text", "") or artist.get("name", "Unknown")
            else:
                artist_name = str(artist) if artist else "Unknown"
            
            album = track.get("album", {})
            if isinstance(album, dict):
                album_name = album.get("#text", "") or album.get("name", "")
            else:
                album_name = str(album) if album else ""
            
            # Get artwork URL (largest available)
            images = track.get("image", [])
            artwork_url = ""
            if images:
                # Last image is usually the largest
                for img in reversed(images):
                    if isinstance(img, dict) and img.get("#text"):
                        artwork_url = img["#text"]
                        break
            
            # Track URL
            track_url = track.get("url", "")
            
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
                status = "LAST PLAYED"
            
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
            logger.warning("Last.fm API request timed out")
            if self._cache:
                return PluginResult(available=True, data=self._cache)
            return PluginResult(
                available=False,
                error="Request timed out"
            )
        except requests.exceptions.RequestException as e:
            logger.exception("Error fetching Last.fm data")
            if self._cache:
                return PluginResult(available=True, data=self._cache)
            return PluginResult(
                available=False,
                error=f"Network error: {str(e)}"
            )
        except Exception as e:
            logger.exception("Unexpected error fetching Last.fm data")
            if self._cache:
                return PluginResult(available=True, data=self._cache)
            return PluginResult(
                available=False,
                error=str(e)
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
        
        # Title (may need to truncate/wrap)
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
        logger.info(f"Plugin {self.plugin_id} cleanup")


# Export the plugin class
Plugin = LastFmPlugin
