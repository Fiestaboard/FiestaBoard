"""Allergy & Health plugin for FiestaBoard.

Displays allergy levels (pollen counts), air quality, and health risk
indicators using the Open-Meteo Air Quality API.
"""

from typing import Any, Dict, List, Optional, Tuple
import logging
import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# Default: San Francisco
DEFAULT_LAT = 37.7749
DEFAULT_LON = -122.4194

# Open-Meteo Air Quality API
AIR_QUALITY_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Pollen thresholds (grains/m3) for allergy risk classification
# Based on NAB (National Allergy Bureau) standards
GRASS_THRESHOLDS = (20, 100, 200)     # moderate, high, very high
TREE_THRESHOLDS = (50, 200, 500)      # moderate, high, very high
WEED_THRESHOLDS = (20, 80, 200)       # moderate, high, very high

# AQI categories (US EPA)
AQI_CATEGORIES = [
    (50, "GOOD", "GREEN"),
    (100, "MODERATE", "YELLOW"),
    (150, "UNHEALTHY-S", "ORANGE"),    # Unhealthy for Sensitive Groups
    (200, "UNHEALTHY", "RED"),
    (300, "VERY BAD", "VIOLET"),
    (500, "HAZARDOUS", "VIOLET"),
]

# Maximum health risk scale value
MAX_RISK_SCALE = 12.0


class HealthPlugin(PluginBase):
    """Allergy & Health plugin.

    Fetches pollen counts, air quality, and calculates health risk
    indicators from Open-Meteo Air Quality API data.
    """

    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the health plugin."""
        super().__init__(manifest)

    @property
    def plugin_id(self) -> str:
        return "health"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate health plugin configuration."""
        errors = []

        lat = config.get("latitude", DEFAULT_LAT)
        lon = config.get("longitude", DEFAULT_LON)

        try:
            lat = float(lat)
            if not (-90 <= lat <= 90):
                errors.append("Latitude must be between -90 and 90")
        except (TypeError, ValueError):
            errors.append("Latitude must be a valid number")

        try:
            lon = float(lon)
            if not (-180 <= lon <= 180):
                errors.append("Longitude must be between -180 and 180")
        except (TypeError, ValueError):
            errors.append("Longitude must be a valid number")

        return errors

    @staticmethod
    def calculate_allergy_risk(grass: float, tree: float, weed: float) -> Tuple[str, str]:
        """Calculate overall allergy risk from pollen counts.

        Args:
            grass: Grass pollen count (grains/m3).
            tree: Tree pollen count (grains/m3).
            weed: Weed pollen count (grains/m3).

        Returns:
            Tuple of (risk_label, color_name).
        """
        max_level = 0

        for value, thresholds in [
            (grass, GRASS_THRESHOLDS),
            (tree, TREE_THRESHOLDS),
            (weed, WEED_THRESHOLDS),
        ]:
            if value >= thresholds[2]:
                max_level = max(max_level, 4)
            elif value >= thresholds[1]:
                max_level = max(max_level, 3)
            elif value >= thresholds[0]:
                max_level = max(max_level, 2)
            elif value > 0:
                max_level = max(max_level, 1)

        labels = [
            ("LOW", "GREEN"),
            ("LOW", "GREEN"),
            ("MODERATE", "YELLOW"),
            ("HIGH", "ORANGE"),
            ("VERY HIGH", "RED"),
        ]
        return labels[max_level]

    @staticmethod
    def calculate_respiratory_risk(
        aqi: float, pm25: float, total_pollen: float
    ) -> float:
        """Calculate respiratory health risk on a 0-12 scale.

        Based on AQI, PM2.5, and total pollen exposure.

        Args:
            aqi: US AQI value.
            pm25: PM2.5 concentration (ug/m3).
            total_pollen: Sum of all pollen counts (grains/m3).

        Returns:
            Risk score from 0.0 to 12.0.
        """
        # AQI component (0-6 points): linear scale where 300+ = max
        aqi_score = min(aqi / 300.0, 1.0) * 6.0

        # PM2.5 component (0-3 points): linear scale where 150+ ug/m3 = max
        pm25_score = min(pm25 / 150.0, 1.0) * 3.0

        # Pollen component (0-3 points): linear scale where 500+ grains/m3 = max
        pollen_score = min(total_pollen / 500.0, 1.0) * 3.0

        total = aqi_score + pm25_score + pollen_score
        return round(max(0.0, min(total, MAX_RISK_SCALE)), 1)

    @staticmethod
    def calculate_flu_risk(aqi: float, pm25: float, pm10: float) -> float:
        """Calculate flu risk indicator on a 0-12 scale.

        Higher air pollution is associated with increased respiratory
        illness transmission and susceptibility.

        Args:
            aqi: US AQI value.
            pm25: PM2.5 concentration (ug/m3).
            pm10: PM10 concentration (ug/m3).

        Returns:
            Risk score from 0.0 to 12.0.
        """
        # AQI component (0-6 points)
        aqi_score = min(aqi / 300.0, 1.0) * 6.0

        # PM2.5 component (0-3 points)
        pm25_score = min(pm25 / 150.0, 1.0) * 3.0

        # PM10 component (0-3 points): linear scale where 300+ ug/m3 = max
        pm10_score = min(pm10 / 300.0, 1.0) * 3.0

        total = aqi_score + pm25_score + pm10_score
        return round(max(0.0, min(total, MAX_RISK_SCALE)), 1)

    @staticmethod
    def calculate_cough_risk(
        aqi: float, pm25: float, total_pollen: float
    ) -> float:
        """Calculate cough risk indicator on a 0-12 scale.

        Based on irritants that trigger coughing: air pollution and
        allergen exposure.

        Args:
            aqi: US AQI value.
            pm25: PM2.5 concentration (ug/m3).
            total_pollen: Sum of all pollen counts (grains/m3).

        Returns:
            Risk score from 0.0 to 12.0.
        """
        # AQI component (0-4 points)
        aqi_score = min(aqi / 200.0, 1.0) * 4.0

        # PM2.5 component (0-4 points): primary cough irritant
        pm25_score = min(pm25 / 100.0, 1.0) * 4.0

        # Pollen component (0-4 points): allergic cough trigger
        pollen_score = min(total_pollen / 400.0, 1.0) * 4.0

        total = aqi_score + pm25_score + pollen_score
        return round(max(0.0, min(total, MAX_RISK_SCALE)), 1)

    def _fetch_air_quality_data(self) -> Optional[Dict]:
        """Fetch air quality and pollen data from Open-Meteo."""
        lat = self.config.get("latitude", DEFAULT_LAT)
        lon = self.config.get("longitude", DEFAULT_LON)

        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join([
                "european_aqi",
                "us_aqi",
                "pm2_5",
                "pm10",
                "grass_pollen",
                "birch_pollen",
                "ragweed_pollen",
                "alder_pollen",
            ]),
        }

        try:
            response = requests.get(AIR_QUALITY_API_URL, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch air quality data: {e}")
            return None

    @staticmethod
    def _color_to_code(color: str) -> int:
        """Map color name to board character code."""
        color_map = {
            "GREEN": 66,
            "YELLOW": 65,
            "ORANGE": 64,
            "RED": 63,
            "VIOLET": 68,
        }
        return color_map.get(color.upper(), 66)

    def fetch_data(self) -> PluginResult:
        """Fetch allergy and health data."""
        api_data = self._fetch_air_quality_data()

        if not api_data:
            return PluginResult(
                available=False,
                error="Failed to fetch air quality data",
            )

        try:
            current = api_data.get("current", {})

            # Extract pollen counts
            grass_pollen = current.get("grass_pollen") or 0
            # Combine birch + alder as "tree" pollen
            birch = current.get("birch_pollen") or 0
            alder = current.get("alder_pollen") or 0
            tree_pollen = birch + alder
            weed_pollen = current.get("ragweed_pollen") or 0

            # Extract air quality
            us_aqi = current.get("us_aqi") or 0
            european_aqi = current.get("european_aqi") or 0
            pm25 = current.get("pm2_5") or 0
            pm10 = current.get("pm10") or 0

            # Calculate allergy risk
            allergy_label, allergy_color = self.calculate_allergy_risk(
                grass_pollen, tree_pollen, weed_pollen
            )

            # Calculate health risk indicators
            total_pollen = grass_pollen + tree_pollen + weed_pollen
            respiratory_risk = self.calculate_respiratory_risk(
                us_aqi, pm25, total_pollen
            )
            flu_risk = self.calculate_flu_risk(us_aqi, pm25, pm10)
            cough_risk = self.calculate_cough_risk(us_aqi, pm25, total_pollen)

            # Build color codes
            allergy_color_code = self._color_to_code(allergy_color)

            data = {
                "grass_pollen": round(grass_pollen),
                "tree_pollen": round(tree_pollen),
                "weed_pollen": round(weed_pollen),
                "aqi": us_aqi,
                "european_aqi": european_aqi,
                "pm25": round(pm25, 1),
                "pm10": round(pm10, 1),
                "allergy_risk": allergy_label,
                "allergy_risk_color": f"{{{allergy_color_code}}}",
                "respiratory_risk": respiratory_risk,
                "flu_risk": flu_risk,
                "cough_risk": cough_risk,
                "formatted": f"ALLERGY: {allergy_label}",
            }

            return PluginResult(available=True, data=data)

        except Exception as e:
            logger.exception("Error processing health data")
            return PluginResult(available=False, error=str(e))

    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted health display."""
        result = self.fetch_data()
        if not result.available or not result.data:
            return None

        d = result.data
        lines = [
            "ALLERGY & HEALTH".center(22),
            f"PPM         0-{int(MAX_RISK_SCALE)}".center(22),
            f"GRASS:{d['grass_pollen']:>4} FLU:{d['flu_risk']:>5}",
            f"TREES:{d['tree_pollen']:>4} COUGH:{d['cough_risk']:>3}",
            f"WEEDS:{d['weed_pollen']:>4} RESP:{d['respiratory_risk']:>4}",
            f"AQI:{d['aqi']:>5} EAQI:{d['european_aqi']:>4}",
        ]

        return lines


# Export the plugin class
Plugin = HealthPlugin
