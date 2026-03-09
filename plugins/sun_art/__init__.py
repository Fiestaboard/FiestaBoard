"""Sun Art plugin for FiestaBoard.

Displays a full-screen 6x22 bit image pattern that changes based on the sun's
position throughout the day. Uses latitude/longitude coordinates to calculate
accurate sun positions and generates visual patterns for different sun stages.
"""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
import pytz
from astral import LocationInfo
from astral.sun import sun, elevation, azimuth

from src.plugins.base import PluginBase, PluginResult
from src.config import Config
from src.board_chars import BoardChars

logger = logging.getLogger(__name__)

# Board dimensions
ROWS = 6
COLS = 22

# Sun stage elevation thresholds (in degrees)
STAGE_THRESHOLDS = {
    "night": (-90, -6),      # Below horizon, no twilight
    "dusk": (-6, 0),         # Civil twilight (sun below horizon but sky still lit)
    "sunset": (0, 5),        # Sun setting (0° to 5°)
    "afternoon": (5, 30),    # Afternoon sun (5° to 30°)
    "noon": (30, 90),        # High sun (30° to 90°)
    "morning": (5, 30),      # Morning sun (5° to 30°)
    "sunrise": (0, 5),       # Sun rising (0° to 5°)
    "dawn": (-6, 0),         # Civil dawn (sun below horizon but sky lighting)
}


class SunArtPlugin(PluginBase):
    """Sun art plugin.
    
    Generates full-screen 6x22 grid patterns representing the sun's position
    throughout the day. Patterns change based on sun elevation angle and time
    relative to sunrise/sunset.
    """
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the sun art plugin."""
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_date: Optional[str] = None
    
    @property
    def plugin_id(self) -> str:
        return "sun_art"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate sun art configuration."""
        errors = []
        
        lat = config.get("latitude")
        lon = config.get("longitude")
        
        if lat is None:
            errors.append("Latitude is required")
        elif not isinstance(lat, (int, float)) or not (-90 <= lat <= 90):
            errors.append("Latitude must be a number between -90 and 90")
        
        if lon is None:
            errors.append("Longitude is required")
        elif not isinstance(lon, (int, float)) or not (-180 <= lon <= 180):
            errors.append("Longitude must be a number between -180 and 180")
        
        refresh_seconds = config.get("refresh_seconds", 300)
        if not isinstance(refresh_seconds, int) or refresh_seconds < 60:
            errors.append("Refresh interval must be at least 60 seconds")
        
        return errors
    
    def fetch_data(self) -> PluginResult:
        """Fetch sun art data and generate pattern."""
        lat = self.config.get("latitude")
        lon = self.config.get("longitude")
        
        if lat is None or lon is None:
            return PluginResult(
                available=False,
                error="Latitude and longitude are required"
            )
        
        try:
            # Get timezone from general settings
            timezone_str = Config.GENERAL_TIMEZONE
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)
            
            # Check cache (recalculate at midnight)
            today = now.strftime("%Y-%m-%d")
            if self._cache and self._cache_date == today:
                # Use cached data if still valid
                refresh_seconds = self.config.get("refresh_seconds", 300)
                cache_age = (now - self._cache.get("calculated_at", now)).total_seconds()
                if cache_age < refresh_seconds:
                    logger.debug(f"Using cached sun art data (age: {cache_age:.0f}s)")
                    return PluginResult(available=True, data=self._cache)
            
            # Calculate sun position
            sun_data = self._calculate_sun_position(lat, lon, now, tz)
            
            # Determine sun stage
            sun_stage = self._determine_sun_stage(
                sun_data["elevation"],
                sun_data["is_rising"]
            )
            
            # Generate pattern
            pattern_array = self._generate_pattern(sun_stage, sun_data["elevation"])
            pattern_string = self._pattern_to_string(pattern_array)
            
            # Calculate time to next sunrise/sunset
            time_to_sunrise, time_to_sunset = self._calculate_next_events(
                lat, lon, now, tz
            )
            
            # Prepare result data
            data = {
                "sun_art": pattern_string,
                "sun_art_array": pattern_array,  # Note: This will be serialized as JSON
                "sun_stage": sun_stage,
                "sun_position": round(sun_data["elevation"], 1),
                "is_daytime": sun_data["elevation"] > 0,
                "time_to_sunrise": time_to_sunrise,
                "time_to_sunset": time_to_sunset,
            }
            
            # Cache the result
            self._cache = data.copy()
            self._cache["calculated_at"] = now
            self._cache_date = today
            
            return PluginResult(
                available=True,
                data=data
            )
            
        except Exception as e:
            logger.exception("Error fetching sun art data")
            return PluginResult(
                available=False,
                error=str(e)
            )
    
    def _calculate_sun_position(
        self, lat: float, lon: float, dt: datetime, tz: pytz.BaseTzInfo
    ) -> Dict[str, Any]:
        """Calculate current sun position.
        
        Args:
            lat: Latitude
            lon: Longitude
            dt: Current datetime (timezone-aware)
            tz: Timezone object
            
        Returns:
            Dictionary with elevation, azimuth, and is_rising flag
        """
        # Create location info
        location = LocationInfo(
            name="Location",
            region="Region",
            timezone=tz.zone,
            latitude=lat,
            longitude=lon
        )
        
        # Get sun data for today
        s = sun(location.observer, date=dt.date(), tzinfo=tz)
        
        # Calculate elevation and azimuth angles
        sun_elevation = elevation(location.observer, dt)
        sun_azimuth = azimuth(location.observer, dt)
        
        # Determine if sun is rising or setting
        # Compare current time to sunrise and sunset
        sunrise = s["sunrise"]
        sunset = s["sunset"]
        
        # If before sunrise or after sunset, sun is below horizon
        if dt < sunrise:
            # Before sunrise - sun is rising (but below horizon)
            is_rising = True
        elif dt > sunset:
            # After sunset - sun is setting (below horizon)
            is_rising = False
        else:
            # During day - determine if before or after solar noon
            noon = s["noon"]
            is_rising = dt < noon
        
        return {
            "elevation": sun_elevation,
            "azimuth": sun_azimuth,
            "is_rising": is_rising,
            "sunrise": sunrise,
            "sunset": sunset,
            "noon": s["noon"],
        }
    
    def _determine_sun_stage(self, elevation: float, is_rising: bool) -> str:
        """Determine current sun stage based on elevation and direction.
        
        Uses 11 stages for smooth visual progression:
        Rising: night -> late_night -> dawn -> early_sunrise -> sunrise -> morning -> noon
        Setting: noon -> afternoon -> sunset -> late_sunset -> dusk -> twilight -> night
        
        Args:
            elevation: Sun elevation angle in degrees
            is_rising: True if sun is rising, False if setting
            
        Returns:
            Sun stage name (one of 11 stages)
        """
        if is_rising:
            # Sun is rising (before solar noon)
            if elevation < -12:
                return "night"
            elif elevation < -6:
                return "late_night"
            elif elevation < -1:
                return "dawn"
            elif elevation < 3:
                return "early_sunrise"
            elif elevation < 10:
                return "sunrise"
            elif elevation < 30:
                return "morning"
            else:
                return "noon"
        else:
            # Sun is setting (after solar noon)
            if elevation >= 30:
                return "noon"
            elif elevation >= 10:
                return "afternoon"
            elif elevation >= 3:
                return "sunset"
            elif elevation >= -1:
                return "late_sunset"
            elif elevation >= -6:
                return "dusk"
            elif elevation >= -12:
                return "twilight"
            else:
                return "night"
    
    def _generate_pattern(self, stage: str, elevation: float) -> List[List[int]]:
        """Generate 6x22 pattern for given sun stage.
        
        Uses 11 stages showing sun rising/setting line by line:
        night -> late_night -> dawn -> early_sunrise -> sunrise -> morning -> noon
        noon -> afternoon -> sunset -> late_sunset -> dusk -> twilight -> night
        
        Args:
            stage: Sun stage name (one of 11 stages)
            elevation: Sun elevation angle (unused - patterns are hardcoded)
            
        Returns:
            6x22 array of character codes
        """
        # Color shortcuts for readability
        K = BoardChars.BLACK   # 70
        R = BoardChars.RED     # 63
        O = BoardChars.ORANGE  # 64
        Y = BoardChars.YELLOW  # 65
        B = BoardChars.BLUE    # 67
        V = BoardChars.VIOLET  # 68
        W = BoardChars.WHITE   # 69
        
        # Hardcoded patterns for each of 11 stages (6 rows x 22 columns)
        # Sun rises from bottom to top, then sets from top to bottom
        # Based on reference images from issue #115
        
        patterns = {
            # 1. NIGHT: Black with white stars scattered
            "night": [
                [K,K,K,W,K,K,K,K,K,K,K,K,K,K,K,K,K,W,K,K,K,K],
                [K,K,K,K,K,K,K,K,W,K,K,K,K,K,K,K,K,K,K,K,K,K],
                [K,K,K,K,K,K,K,K,K,K,K,K,W,K,K,K,K,K,K,K,W,K],
                [K,W,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K],
                [K,K,K,K,K,K,K,K,K,K,K,K,K,K,K,W,K,K,K,K,K,K],
                [K,K,K,K,K,W,K,K,K,K,K,K,K,K,K,K,K,K,K,W,K,K],
            ],
            
            # 2. LATE_NIGHT: Stars with faint violet/orange glow at horizon
            "late_night": [
                [K,K,K,W,K,K,K,K,K,K,K,K,K,K,K,K,K,W,K,K,K,K],
                [K,K,K,K,K,K,K,K,W,K,K,K,K,K,K,K,K,K,K,K,K,K],
                [K,K,K,K,K,K,K,K,K,K,K,K,W,K,K,K,K,K,K,K,W,K],
                [K,W,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K,K],
                [V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V],
                [V,V,V,V,V,O,O,O,O,O,O,O,O,O,O,O,O,V,V,V,V,V],
            ],
            
            # 3. DAWN: Purple/violet sky, orange glow at horizon, sun just below
            "dawn": [
                [V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V],
                [V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V],
                [V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V],
                [V,V,V,V,V,O,O,O,O,O,O,O,O,O,O,O,O,V,V,V,V,V],
                [O,O,O,O,O,O,O,O,Y,Y,Y,Y,Y,Y,O,O,O,O,O,O,O,O],
                [O,O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O,O],
            ],
            
            # 4. EARLY_SUNRISE: Sun peeking (1 row), orange/violet sky
            "early_sunrise": [
                [V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V],
                [V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V],
                [O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O],
                [O,O,O,O,O,O,O,O,Y,Y,Y,Y,Y,Y,O,O,O,O,O,O,O,O],
                [O,O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O,O],
                [O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O],
            ],
            
            # 5. SUNRISE: Sun rising, transitioning to morning style
            "sunrise": [
                [B,B,B,B,B,B,O,Y,Y,Y,Y,Y,Y,Y,Y,O,B,B,B,B,B,B],
                [B,B,B,B,B,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,B,B,B,B,B],
                [O,O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O,O],
                [O,O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O,O],
                [O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O],
                [O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O],
            ],
            
            # 6. MORNING: Matches reference image 2 - blue sides, yellow sun column, orange bottom sides
            "morning": [
                [B,B,B,B,B,B,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,B,B,B,B,B,B],
                [B,B,B,B,B,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,B,B,B,B,B],
                [B,B,B,B,B,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,B,B,B,B,B],
                [O,O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O,O],
                [O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O],
                [O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O],
            ],
            
            # 7. NOON: Brightest - blue sides, white/yellow sun column, orange bottom sides
            "noon": [
                [B,B,B,B,B,Y,Y,W,W,W,W,W,W,W,W,Y,Y,B,B,B,B,B],
                [B,B,B,B,B,Y,W,W,W,W,W,W,W,W,W,W,Y,B,B,B,B,B],
                [B,B,B,B,B,Y,Y,W,W,W,W,W,W,W,W,Y,Y,B,B,B,B,B],
                [O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O],
                [O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O],
                [O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O],
            ],
            
            # 8. AFTERNOON: Same as morning - blue sides, yellow sun column, orange bottom sides
            "afternoon": [
                [B,B,B,B,B,B,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,B,B,B,B,B,B],
                [B,B,B,B,B,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,B,B,B,B,B],
                [B,B,B,B,B,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,B,B,B,B,B],
                [O,O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O,O],
                [O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O],
                [O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O],
            ],
            
            # 9. SUNSET: Matches reference image 3 - orange sky, yellow sun, red accents, purple corners
            "sunset": [
                [O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O,O],
                [O,O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O,O],
                [R,R,R,R,R,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,R,R,R,R,R],
                [R,R,R,R,R,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,R,R,R,R,R],
                [O,O,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,O,O],
                [V,V,O,O,O,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,Y,O,O,O,V,V],
            ],
            
            # 10. LATE_SUNSET: Sun almost gone, transitioning to dusk style
            "late_sunset": [
                [R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R],
                [R,R,R,R,R,R,O,O,O,O,O,O,O,O,O,O,R,R,R,R,R,R],
                [R,R,R,R,V,V,V,V,V,V,V,V,V,V,V,V,V,V,R,R,R,R],
                [V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V],
                [V,V,V,V,V,V,V,V,Y,Y,Y,Y,Y,Y,V,V,V,V,V,V,V,V],
                [V,V,V,V,V,V,V,Y,Y,Y,Y,Y,Y,Y,Y,V,V,V,V,V,V,V],
            ],
            
            # 11. DUSK: Matches reference image 1 - red top, orange band, purple middle, yellow sun at bottom
            "dusk": [
                [R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R,R],
                [R,R,R,R,R,R,O,O,O,O,O,O,O,O,O,O,R,R,R,R,R,R],
                [R,R,R,R,V,V,V,V,V,V,V,V,V,V,V,V,V,V,R,R,R,R],
                [V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V],
                [V,V,V,V,V,V,V,V,Y,Y,Y,Y,Y,Y,V,V,V,V,V,V,V,V],
                [V,V,V,V,V,V,V,Y,Y,Y,Y,Y,Y,Y,Y,V,V,V,V,V,V,V],
            ],
            
            # 12. TWILIGHT: Fading to night, stars appearing
            "twilight": [
                [K,K,K,W,K,K,K,K,K,K,K,K,K,K,K,K,K,W,K,K,K,K],
                [K,K,K,K,K,K,K,K,W,K,K,K,K,K,K,K,K,K,K,K,K,K],
                [V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V],
                [V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V],
                [V,V,V,V,V,V,O,O,O,O,O,O,O,O,O,O,V,V,V,V,V,V],
                [V,V,V,V,V,O,O,O,Y,Y,Y,Y,Y,Y,O,O,O,V,V,V,V,V],
            ],
        }
        
        return patterns.get(stage, patterns["night"])
    
    def _pattern_to_string(self, pattern: List[List[int]]) -> str:
        """Convert pattern array to string format with color markers.
        
        Args:
            pattern: 6x22 array of character codes
            
        Returns:
            Newline-separated string with color markers
        """
        lines = []
        color_map = {
            BoardChars.RED: "{red}",
            BoardChars.ORANGE: "{orange}",
            BoardChars.YELLOW: "{yellow}",
            BoardChars.GREEN: "{green}",
            BoardChars.BLUE: "{blue}",
            BoardChars.VIOLET: "{violet}",
            BoardChars.WHITE: "{white}",
            BoardChars.BLACK: "{black}",
        }
        
        for row in pattern:
            line = ""
            for code in row:
                if code in color_map:
                    line += color_map[code]
                elif code == BoardChars.SPACE:
                    line += " "
                else:
                    # Character code - convert to character
                    char = self._code_to_char(code)
                    line += char
            lines.append(line)
        
        return "\n".join(lines)
    
    def _code_to_char(self, code: int) -> str:
        """Convert character code to character string.
        
        Args:
            code: Character code (0-71)
            
        Returns:
            Character string
        """
        if 1 <= code <= 26:
            return chr(ord('A') + code - 1)
        elif 27 <= code <= 35:
            return str(code - 26)
        elif code == 36:
            return "0"
        else:
            return " "
    
    def _calculate_next_events(
        self, lat: float, lon: float, now: datetime, tz: pytz.BaseTzInfo
    ) -> Tuple[str, str]:
        """Calculate time until next sunrise and sunset.
        
        Args:
            lat: Latitude
            lon: Longitude
            now: Current datetime
            tz: Timezone
            
        Returns:
            Tuple of (time_to_sunrise, time_to_sunset) as "HH:MM" strings
        """
        location = LocationInfo(
            name="Location",
            region="Region",
            timezone=tz.zone,
            latitude=lat,
            longitude=lon
        )
        
        # Get today's sun events
        s_today = sun(location.observer, date=now.date(), tzinfo=tz)
        sunrise_today = s_today["sunrise"]
        sunset_today = s_today["sunset"]
        
        # Get tomorrow's sun events
        tomorrow = now.date() + timedelta(days=1)
        s_tomorrow = sun(location.observer, date=tomorrow, tzinfo=tz)
        sunrise_tomorrow = s_tomorrow["sunrise"]
        sunset_tomorrow = s_tomorrow["sunset"]
        
        # Determine next sunrise
        if now < sunrise_today:
            next_sunrise = sunrise_today
        else:
            next_sunrise = sunrise_tomorrow
        
        # Determine next sunset
        if now < sunset_today:
            next_sunset = sunset_today
        else:
            next_sunset = sunset_tomorrow
        
        # Calculate time differences
        delta_sunrise = next_sunrise - now
        delta_sunset = next_sunset - now
        
        # Format as HH:MM
        def format_timedelta(td: timedelta) -> str:
            total_seconds = int(td.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours:02d}:{minutes:02d}"
        
        return format_timedelta(delta_sunrise), format_timedelta(delta_sunset)


# Export the plugin class
Plugin = SunArtPlugin
