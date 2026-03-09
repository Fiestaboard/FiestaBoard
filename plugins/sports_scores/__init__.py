"""Sports Scores plugin for FiestaBoard.

Displays recent sports match scores from NFL, Soccer, NHL, and NBA
using TheSportsDB API.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import logging
import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# Sport name to TheSportsDB identifier mapping
SPORT_MAP = {
    "NFL": "American%20Football",
    "Soccer": "Soccer",
    "NHL": "Ice%20Hockey",
    "NBA": "Basketball",
}

# TheSportsDB API base URL
API_BASE_URL_V1 = "https://www.thesportsdb.com/api/v1/json"
API_BASE_URL_V2 = "https://www.thesportsdb.com/api/v2/json"
FREE_API_KEY = "123"


class SportsScoresPlugin(PluginBase):
    """Sports scores plugin.
    
    Fetches recent sports match scores from TheSportsDB API.
    Supports NFL, Soccer, NHL, and NBA.
    """
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the sports scores plugin."""
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
    
    @property
    def plugin_id(self) -> str:
        return "sports_scores"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate sports scores configuration."""
        errors = []
        
        sports = config.get("sports", [])
        if not sports:
            errors.append("At least one sport must be selected")
        else:
            valid_sports = set(SPORT_MAP.keys())
            invalid_sports = [s for s in sports if s not in valid_sports]
            if invalid_sports:
                errors.append(f"Invalid sports: {', '.join(invalid_sports)}. Valid options: {', '.join(valid_sports)}")
        
        max_games_raw = config.get("max_games_per_sport")
        if max_games_raw is not None:
            try:
                max_games = int(max_games_raw)
                if max_games < 1 or max_games > 10:
                    errors.append("max_games_per_sport must be between 1 and 10")
            except (ValueError, TypeError):
                errors.append("max_games_per_sport must be a valid number between 1 and 10")
        
        return errors
    
    def fetch_data(self) -> PluginResult:
        """Fetch sports scores for all configured sports."""
        sports = self.config.get("sports", [])
        if not sports:
            return PluginResult(
                available=False,
                error="No sports selected"
            )
        
        api_key = self.config.get("api_key", "").strip()
        if not api_key:
            api_key = FREE_API_KEY
        
        max_games_per_sport = self.config.get("max_games_per_sport", 3)
        
        try:
            # Check cache first - if we have recent cache, use it to avoid rate limits
            # Cache is valid for refresh_seconds (default 300s = 5 min)
            refresh_seconds = self.config.get("refresh_seconds", 300)
            if self._cache and self._cache.get("games"):
                last_updated = self._cache.get("last_updated", "")
                if last_updated:
                    try:
                        cache_time = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                        age_seconds = (datetime.now(timezone.utc) - cache_time).total_seconds()
                        if age_seconds < refresh_seconds:
                            logger.debug(f"Using cached data (age: {age_seconds:.0f}s < {refresh_seconds}s)")
                            return PluginResult(available=True, data=self._cache)
                    except Exception:
                        pass  # If cache time parsing fails, continue to fetch
            
            all_games = []
            rate_limited = False
            
            for sport in sports:
                if sport not in SPORT_MAP:
                    logger.warning(f"Unknown sport: {sport}, skipping")
                    continue
                
                sport_id = SPORT_MAP[sport]
                games = self._fetch_sport_scores(sport, sport_id, api_key, max_games_per_sport)
                
                # Check if we got rate limited (empty result)
                if not games and sport == sports[0]:
                    # If first sport returns empty, might be rate limited
                    # Check if we have cached data to return
                    if self._cache and self._cache.get("games"):
                        logger.info("Rate limited or no data - returning cached data")
                        rate_limited = True
                        break
                
                all_games.extend(games)
                
                # Add delay between sports to avoid rate limits (free API: 30 req/min = 1 req per 2s)
                # Wait 2.5 seconds between sports to stay safely under limit
                if sport != sports[-1]:  # Don't delay after last sport
                    import time
                    time.sleep(2.5)
            
            # If rate limited and we have cache, return cache
            if rate_limited and self._cache and self._cache.get("games"):
                logger.info("Returning cached data due to rate limiting")
                return PluginResult(available=True, data=self._cache)
            
            if not all_games:
                # If no games but we have cache, return cache
                if self._cache and self._cache.get("games"):
                    logger.info("No new games found, returning cached data")
                    return PluginResult(available=True, data=self._cache)
                return PluginResult(
                    available=False,
                    error="No games found for selected sports"
                )
            
            # Sort all games by date (most recent first)
            all_games.sort(key=lambda g: g.get("date", ""), reverse=True)
            
            # Primary game (first one)
            primary = all_games[0] if all_games else {}
            
            data = {
                # Primary game fields
                "sport": primary.get("sport", ""),
                "team1": primary.get("team1", ""),
                "team2": primary.get("team2", ""),
                "score1": primary.get("score1", 0),
                "score2": primary.get("score2", 0),
                "status": primary.get("status", ""),
                "date": primary.get("date", ""),
                "time": primary.get("time", ""),
                "formatted": primary.get("formatted", ""),
                # Aggregate
                "sport_count": len(sports),
                "game_count": len(all_games),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                # Array of all games
                "games": all_games,
            }
            
            self._cache = data
            return PluginResult(available=True, data=data)
            
        except Exception as e:
            logger.exception("Error fetching sports scores")
            # Return cache if available even on error
            if self._cache and self._cache.get("games"):
                logger.info("Error occurred, returning cached data")
                return PluginResult(available=True, data=self._cache)
            return PluginResult(available=False, error=str(e))
    
    def _fetch_sport_scores(self, sport_name: str, sport_id: str, api_key: str, max_games: int) -> List[Dict[str, Any]]:
        """Fetch scores for a specific sport."""
        try:
            # Try V2 livescore endpoint first if we have a premium API key (not the free "123" key)
            if api_key and api_key != FREE_API_KEY:
                games = self._fetch_v2_livescore(sport_name, sport_id, api_key, max_games)
                if games:
                    return games
            
            # Fall back to V1 API - use eventsday.php to get events by sport and date
            # Try today's date first, then yesterday if no games found
            from datetime import timedelta
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            
            # Try today first
            url = f"{API_BASE_URL_V1}/{api_key}/eventsday.php"
            params = {"d": today.strftime("%Y-%m-%d"), "s": sport_id}
            
            # Log the full URL for debugging
            full_url = f"{url}?d={today.strftime('%Y-%m-%d')}&s={sport_id}"
            logger.info(f"Fetching {sport_name} scores from: {full_url}")
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 429:
                logger.warning(f"Rate limit hit for {sport_name} - API limit exceeded")
                # Return empty to trigger cache fallback in fetch_data
                return []
            
            # Don't raise on non-200, check status manually
            if response.status_code != 200:
                logger.warning(f"API returned status {response.status_code} for {sport_name}")
                # Try to parse error response
                try:
                    error_data = response.json()
                    logger.debug(f"Error response: {error_data}")
                except Exception:
                    logger.debug(f"Response text: {response.text[:200]}")
                return []
            
            # Check if response is actually JSON
            content_type = response.headers.get("content-type", "").lower()
            if "application/json" not in content_type:
                logger.warning(f"Unexpected content type for {sport_name}: {content_type}")
                logger.warning(f"Response text (first 500 chars): {response.text[:500]}")
                # For NFL, try using eventspastleague endpoint as fallback
                if sport_name == "NFL":
                    logger.info(f"Trying eventspastleague endpoint for NFL (league ID 4391)")
                    return self._fetch_nfl_via_league(api_key, max_games)
                return []
            
            # Check if response is empty
            if not response.text or not response.text.strip():
                logger.warning(f"Empty response for {sport_name}")
                return []
            
            try:
                data = response.json()
            except ValueError as e:
                logger.error(f"Failed to parse JSON response for {sport_name}: {e}")
                logger.error(f"Response status: {response.status_code}")
                logger.error(f"Response headers: {dict(response.headers)}")
                logger.error(f"Response text (first 500 chars): {response.text[:500]}")
                logger.error(f"Response text length: {len(response.text)}")
                return []
            
            # Handle case where API returns None for event/events field
            # TheSportsDB API can return either "event" (singular) or "events" (plural)
            events = data.get("event") or data.get("events")
            if events is None:
                logger.debug(f"No event/events field in response for {sport_name} on {today}. Response keys: {list(data.keys())}")
                # For NFL, try league endpoint first before trying yesterday
                if sport_name == "NFL":
                    logger.info(f"No events field for NFL, trying league endpoint")
                    return self._fetch_nfl_via_league(api_key, max_games)
                # Try yesterday's date if today has no events
                logger.info(f"Trying yesterday's date for {sport_name}: {yesterday}")
                params = {"d": yesterday.strftime("%Y-%m-%d"), "s": sport_id}
                full_url = f"{url}?d={yesterday.strftime('%Y-%m-%d')}&s={sport_id}"
                logger.info(f"Fetching {sport_name} scores from: {full_url}")
                
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        events = data.get("event") or data.get("events")
                        if events is None:
                            logger.debug(f"No events found for {sport_name} on {yesterday} either")
                            # For NFL, try league endpoint as last resort
                            if sport_name == "NFL":
                                return self._fetch_nfl_via_league(api_key, max_games)
                            return []
                    except ValueError:
                        logger.error(f"Failed to parse JSON response for {sport_name} (yesterday)")
                        # For NFL, try league endpoint as fallback
                        if sport_name == "NFL":
                            return self._fetch_nfl_via_league(api_key, max_games)
                        return []
                else:
                    # For NFL, try league endpoint as fallback
                    if sport_name == "NFL":
                        return self._fetch_nfl_via_league(api_key, max_games)
                    return []
            
            if not isinstance(events, list):
                logger.warning(f"Events is not a list for {sport_name}: {type(events)}")
                return []
            
            if not events:
                logger.debug(f"No events found for {sport_name}")
                # For NFL, try league-based endpoint as fallback
                if sport_name == "NFL":
                    logger.info(f"No events found via eventsday for NFL, trying league endpoint")
                    return self._fetch_nfl_via_league(api_key, max_games)
                return []
            
            logger.debug(f"Found {len(events)} events for {sport_name}")
            
            games = []
            is_free_api = (api_key == FREE_API_KEY or not api_key or api_key == "")
            
            # For free API, we need to check more events since we filter out games without scores
            # For premium API, we can use the normal limit
            max_events_to_check = max_games * 10 if is_free_api else max_games * 2
            
            parsed_count = 0
            filtered_count = 0
            
            for event in events[:max_events_to_check]:
                game = self._parse_event(event, sport_name)
                if game:
                    parsed_count += 1
                    # For free API, only include games that have scores (skip scheduled games)
                    # For premium API, include all games
                    if is_free_api:
                        # Only include games with actual scores (not 0-0)
                        score1 = game.get("score1", 0)
                        score2 = game.get("score2", 0)
                        if score1 > 0 or score2 > 0:
                            games.append(game)
                        else:
                            filtered_count += 1
                    else:
                        # Premium API: include all games
                        games.append(game)
                    
                    # Stop once we have enough games
                    if len(games) >= max_games:
                        break
            
            if is_free_api:
                if parsed_count > 0 and len(games) == 0:
                    logger.warning(f"Free API: Parsed {parsed_count} games for {sport_name}, but all had 0-0 scores (filtered {filtered_count})")
                    # Try previous dates to find games with scores
                    # We already tried today and yesterday in the main loop, so try day before yesterday
                    from datetime import timedelta
                    day_before = datetime.now().date() - timedelta(days=2)
                    logger.info(f"Trying day before yesterday ({day_before}) for {sport_name} to find games with scores")
                    params = {"d": day_before.strftime("%Y-%m-%d"), "s": sport_id}
                    try:
                        response = requests.get(url, params=params, timeout=10)
                        if response.status_code == 200:
                            try:
                                data = response.json()
                                events_prev = data.get("event") or data.get("events")
                                if events_prev and isinstance(events_prev, list):
                                    logger.debug(f"Found {len(events_prev)} events for {sport_name} on {day_before}")
                                    for event in events_prev[:max_events_to_check]:
                                        game = self._parse_event(event, sport_name)
                                        if game:
                                            score1 = game.get("score1", 0)
                                            score2 = game.get("score2", 0)
                                            if score1 > 0 or score2 > 0:
                                                games.append(game)
                                                if len(games) >= max_games:
                                                    break
                            except ValueError:
                                pass
                    except Exception as e:
                        logger.debug(f"Error fetching previous date for {sport_name}: {e}")
                elif len(games) > 0:
                    logger.info(f"Free API: Found {len(games)} games with scores for {sport_name} (checked {parsed_count} events, filtered {filtered_count})")
            
            return games
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {sport_name} scores: {e}")
            return []
        except Exception as e:
            logger.exception(f"Unexpected error fetching {sport_name} scores")
            return []
    
    def _fetch_v2_livescore(self, sport_name: str, sport_id: str, api_key: str, max_games: int) -> List[Dict[str, Any]]:
        """Fetch live scores using V2 API (premium only)."""
        try:
            # Map sport name to V2 API sport identifier
            v2_sport_map = {
                "NFL": "American_Football",
                "Soccer": "Soccer",
                "NHL": "Ice_Hockey",
                "NBA": "Basketball",
            }
            
            v2_sport = v2_sport_map.get(sport_name, sport_name.lower())
            url = f"{API_BASE_URL_V2}/livescore/{v2_sport}"
            headers = {"X-API-KEY": api_key}
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                logger.debug(f"V2 livescore returned {response.status_code} for {sport_name}")
                return []
            
            try:
                data = response.json()
            except ValueError:
                return []
            
            # V2 livescore returns events in "events" array
            events = data.get("events", [])
            if not events:
                return []
            
            games = []
            for event in events[:max_games]:
                game = self._parse_event(event, sport_name)
                if game:
                    games.append(game)
            
            return games
            
        except Exception as e:
            logger.debug(f"V2 livescore failed for {sport_name}: {e}")
            return []
    
    def _fetch_nfl_via_league(self, api_key: str, max_games: int) -> List[Dict[str, Any]]:
        """Fetch NFL scores using eventspastleague endpoint (NFL League ID: 4391)."""
        try:
            # NFL League ID in TheSportsDB
            nfl_league_id = "4391"
            url = f"{API_BASE_URL_V1}/{api_key}/eventspastleague.php"
            params = {"id": nfl_league_id}
            
            logger.info(f"Fetching NFL scores via league endpoint: {url}?id={nfl_league_id}")
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.warning(f"NFL league endpoint returned status {response.status_code}")
                return []
            
            content_type = response.headers.get("content-type", "").lower()
            if "application/json" not in content_type:
                logger.warning(f"NFL league endpoint returned non-JSON: {content_type}")
                return []
            
            try:
                data = response.json()
            except ValueError as e:
                logger.error(f"Failed to parse JSON from NFL league endpoint: {e}")
                return []
            
            events = data.get("events", [])
            if not events or not isinstance(events, list):
                logger.debug(f"No events found in NFL league response")
                return []
            
            logger.info(f"Found {len(events)} NFL events via league endpoint")
            
            games = []
            is_free_api = (api_key == FREE_API_KEY or not api_key or api_key == "")
            max_events_to_check = max_games * 10 if is_free_api else max_games * 2
            
            for event in events[:max_events_to_check]:
                game = self._parse_event(event, "NFL")
                if game:
                    if is_free_api:
                        score1 = game.get("score1", 0)
                        score2 = game.get("score2", 0)
                        if score1 > 0 or score2 > 0:
                            games.append(game)
                    else:
                        games.append(game)
                    
                    if len(games) >= max_games:
                        break
            
            return games
            
        except Exception as e:
            logger.error(f"Error fetching NFL via league endpoint: {e}")
            return []
    
    def _abbreviate_team_name(self, team_name: str, max_length: int) -> str:
        """Intelligently abbreviate a team name to fit within max_length, removing spaces."""
        # Common abbreviations (apply before removing spaces)
        abbreviations = {
            "United": "Utd",
            "United States": "USA",
            "Football Club": "FC",
            "Athletic Club": "AC",
            "Real": "R",
            "Sporting": "Sp",
            "Association": "Assoc",
            "City": "C",
            "Town": "T",
            "Rovers": "Rov",
            "Wanderers": "Wand",
            "Athletic": "Ath",
            "Sociedad": "Soc",
            "Nijmegen": "Nijm",
            "Utrecht": "Utr",
            "North End": "NE",
            "Eindhoven": "Eind",
            "Wigan": "Wig",
        }
        
        # Apply abbreviations
        abbreviated = team_name
        for full, abbrev in abbreviations.items():
            if full in abbreviated:
                abbreviated = abbreviated.replace(full, abbrev)
        
        # Remove all spaces from abbreviated name
        abbreviated = abbreviated.replace(" ", "")
        
        # If it fits, return it
        if len(abbreviated) <= max_length:
            return abbreviated
        
        # For multi-word teams, try smarter approaches
        words = team_name.split()
        if len(words) > 1:
            # If first word is a common prefix (FC, AC, etc.), keep it and abbreviate rest
            first_word = words[0].upper()
            if first_word in ["FC", "AC", "SC", "CF", "AS"]:
                prefix = first_word
                rest = "".join(words[1:])
                # Abbreviate the rest
                for full, abbrev in abbreviations.items():
                    if full in rest:
                        rest = rest.replace(full, abbrev)
                rest = rest.replace(" ", "")
                combined = prefix + rest
                if len(combined) <= max_length:
                    return combined[:max_length]
                # If still too long, truncate the rest part
                rest_max = max_length - len(prefix)
                if rest_max > 0:
                    return prefix + rest[:rest_max]
            
            # Try acronym: first letter of each word (up to 3 words)
            # Only if we have at least 2 words and acronym would be meaningful
            if len(words) >= 2:
                acronym = "".join([w[0].upper() if w else "" for w in words[:3]])
                if len(acronym) <= max_length and len(acronym) >= 2:
                    return acronym
        
        # Final fallback: truncate
        return abbreviated[:max_length]
    
    def _format_game_string(self, team1: str, team2: str, score1: int, score2: int, max_length: int = 22) -> str:
        """Format a game string with abbreviated team names to fit max_length, with aligned scores."""
        # Always use the score format: "TEAM1 SCORE1 - SCORE2 TEAM2"
        # Use "?" for scores when there are no scores yet
        if score1 > 0 or score2 > 0:
            score_str = f"{score1} - {score2}"
        else:
            # No scores yet - use "?" to maintain format consistency
            score_str = "? - ?"
        
        # Use fixed-width formatting to align scores and fill entire width
        # Format: "TEAM1    SCORE    TEAM2"
        # Calculate available space for teams (scores take ~7-9 chars: "123 - 123" or "? - ?")
        score_width = len(score_str)  # Usually 7-9 chars
        # We need: team1 + space + score + space + team2 = max_length
        # So: team1 + team2 = max_length - score_width - 2 spaces
        available_for_teams = max_length - score_width - 2  # -2 for spaces around score
        
        # Split available space between teams (equal width for alignment)
        team_width = available_for_teams // 2
        
        # Abbreviate team names to fit fixed width
        team1_abbrev = self._abbreviate_team_name(team1, team_width)
        team2_abbrev = self._abbreviate_team_name(team2, team_width)
        
        # Pad team names to fixed width (left-align for team1, right-align for team2)
        # This ensures scores align vertically and fills the entire width
        team1_padded = team1_abbrev[:team_width].ljust(team_width)
        team2_padded = team2_abbrev[:team_width].rjust(team_width)
        
        # Format: "TEAM1    SCORE    TEAM2"
        formatted = f"{team1_padded} {score_str} {team2_padded}"
        
        # Ensure we fill exactly max_length characters (pad with spaces if needed)
        if len(formatted) < max_length:
            # Add extra spaces to team2 padding to fill the width
            extra_spaces = max_length - len(formatted)
            team2_padded = team2_padded + " " * extra_spaces
            formatted = f"{team1_padded} {score_str} {team2_padded}"
        
        return formatted[:max_length]
    
    def _parse_event(self, event: Dict[str, Any], sport_name: str) -> Optional[Dict[str, Any]]:
        """Parse an event from TheSportsDB API response."""
        try:
            team1 = event.get("strHomeTeam", "").strip()
            team2 = event.get("strAwayTeam", "").strip()
            
            if not team1 or not team2:
                return None
            
            # Get scores (may be None or string for scheduled games)
            score1_raw = event.get("intHomeScore")
            score2_raw = event.get("intAwayScore")
            
            # Convert to int, handling None, strings, and integers
            try:
                score1 = int(score1_raw) if score1_raw is not None else 0
            except (ValueError, TypeError):
                score1 = 0
            
            try:
                score2 = int(score2_raw) if score2_raw is not None else 0
            except (ValueError, TypeError):
                score2 = 0
            
            status = event.get("strStatus", "").strip() or "Scheduled"
            date = event.get("dateEvent", "").strip()
            time = event.get("strTime", "").strip()
            
            # Determine team colors based on scores
            # Return color codes in {CODE} format for template engine
            # GREEN (66) if winning, RED (63) if losing, BLUE (67) if no scores yet, YELLOW (65) if tied
            if score1 == 0 and score2 == 0:
                # No scores yet
                team1_color = "{67}"  # Blue
                team2_color = "{67}"  # Blue
            elif score1 > score2:
                team1_color = "{66}"  # Green
                team2_color = "{63}"  # Red
            elif score1 < score2:
                team1_color = "{63}"  # Red
                team2_color = "{66}"  # Green
            else:
                # Tied (both scores > 0 and equal)
                team1_color = "{65}"  # Yellow
                team2_color = "{65}"  # Yellow
            
            # Format the game string with abbreviations to fit 22 chars
            # Create formatted string accounting for color tiles (2 tiles = 2 chars)
            # When used with colors: {{team1_color}}{{formatted}}{{team2_color}}
            # Total width is 22, so formatted should be 20 to account for 2 color tiles
            formatted = self._format_game_string(team1, team2, score1, score2, max_length=20)
            
            # Truncate team names if too long (max 10 chars each for display)
            team1_display = team1[:10] if len(team1) > 10 else team1
            team2_display = team2[:10] if len(team2) > 10 else team2
            
            return {
                "sport": sport_name,
                "team1": team1_display,
                "team2": team2_display,
                "team1_full": team1,
                "team2_full": team2,
                "team1_color": team1_color,
                "team2_color": team2_color,
                "score1": score1,
                "score2": score2,
                "status": status,
                "date": date,
                "time": time,
                "formatted": formatted,
            }
            
        except Exception as e:
            logger.error(f"Error parsing event: {e}")
            return None
    
    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted sports scores display."""
        if not self._cache:
            result = self.fetch_data()
            if not result.available:
                return None
        
        data = self._cache
        if not data:
            return None
        
        games = data.get("games", [])
        lines = ["SPORTS SCORES".center(22), ""]
        
        for game in games[:4]:
            lines.append(game.get("formatted", "")[:22])
        
        while len(lines) < 6:
            lines.append("")
        
        return lines[:6]


# Export the plugin class
Plugin = SportsScoresPlugin
