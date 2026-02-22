"""Bay Wheels (Lyft) GBFS feed integration.

Fetches bike availability data from the Bay Wheels GBFS station_status.json endpoint.
Provides electric and classic bike counts with color-coded status based on availability.
Supports multiple stations with aggregate statistics and location-based discovery.
"""

import logging
import requests
import time
import math
from typing import Optional, Dict, List, Tuple
from ..config import Config

logger = logging.getLogger(__name__)

# Bay Wheels GBFS endpoints
GBFS_BASE_URL = "https://gbfs.baywheels.com/gbfs/en"
STATION_STATUS_URL = f"{GBFS_BASE_URL}/station_status.json"
STATION_INFORMATION_URL = f"{GBFS_BASE_URL}/station_information.json"

# Cache for station information (24 hour TTL)
_station_info_cache: Optional[Dict] = None
_station_info_cache_time: float = 0
STATION_INFO_CACHE_TTL = 24 * 60 * 60  # 24 hours in seconds


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth in kilometers.
    
    Args:
        lat1, lon1: Latitude and longitude of first point
        lat2, lon2: Latitude and longitude of second point
        
    Returns:
        Distance in kilometers
    """
    # Earth radius in kilometers
    R = 6371.0
    
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


class BayWheelsSource:
    """Fetches bike availability data from Bay Wheels GBFS feed."""
    
    def __init__(self, station_ids: List[str]):
        """
        Initialize Bay Wheels source.
        
        Args:
            station_ids: List of station IDs to monitor (e.g., ["station-1", "station-2"])
        """
        # Support both single string (backward compatibility) and list
        if isinstance(station_ids, str):
            self.station_ids = [station_ids]
        else:
            self.station_ids = station_ids if station_ids else []
    
    @staticmethod
    def _get_station_information() -> Optional[Dict]:
        """
        Fetch and cache station information (names, addresses, coordinates).
        Caches for 24 hours to reduce API calls.
        
        Returns:
            Dictionary mapping station_id to station info, or None if fetch failed
        """
        global _station_info_cache, _station_info_cache_time
        
        current_time = time.time()
        
        # Return cached data if still valid
        if _station_info_cache is not None and (current_time - _station_info_cache_time) < STATION_INFO_CACHE_TTL:
            return _station_info_cache
        
        try:
            response = requests.get(STATION_INFORMATION_URL, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            stations = data.get("data", {}).get("stations", [])
            
            # Build a dictionary mapping station_id to station info
            station_info_map = {}
            for station in stations:
                station_id = station.get("station_id")
                if station_id:
                    station_info_map[station_id] = {
                        "station_id": station_id,
                        "name": station.get("name", station_id),
                        "lat": station.get("lat"),
                        "lon": station.get("lon"),
                        "address": station.get("address", ""),
                        "capacity": station.get("capacity", 0),
                    }
            
            # Update cache
            _station_info_cache = station_info_map
            _station_info_cache_time = current_time
            
            logger.debug(f"Cached {len(station_info_map)} stations from station_information.json")
            return station_info_map
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch station information: {e}")
            return _station_info_cache  # Return stale cache if available
        except (KeyError, ValueError) as e:
            logger.error(f"Unexpected response format from station_information.json: {e}")
            return _station_info_cache  # Return stale cache if available
        except Exception as e:
            logger.error(f"Error fetching station information: {e}")
            return _station_info_cache  # Return stale cache if available
    
    def _parse_station_status(self, station_data: Dict) -> Optional[Dict]:
        """
        Parse a single station's status data.
        
        Args:
            station_data: Raw station data from station_status.json
            
        Returns:
            Parsed station data dictionary or None
        """
        try:
            station_id = station_data.get("station_id")
            if not station_id:
                return None
            
            num_bikes_available = station_data.get("num_bikes_available", 0)
            is_renting = station_data.get("is_renting", 1) == 1
            
            # Split bikes by type
            electric_bikes = 0
            classic_bikes = 0
            
            # NEW FORMAT (as of late 2024): API provides num_ebikes_available directly
            if "num_ebikes_available" in station_data:
                electric_bikes = station_data.get("num_ebikes_available", 0)
                # Classic bikes = total - electric
                classic_bikes = num_bikes_available - electric_bikes
            else:
                # OLD FORMAT (fallback): Use vehicle_types_available array
                vehicle_types = station_data.get("vehicle_types_available", [])
                for vehicle_type in vehicle_types:
                    vehicle_type_id = vehicle_type.get("vehicle_type_id", "")
                    count = vehicle_type.get("count", 0)
                    
                    # Bay Wheels uses these IDs for bike types
                    if "electric" in vehicle_type_id.lower() or "boost" in vehicle_type_id.lower():
                        electric_bikes += count
                    elif "classic" in vehicle_type_id.lower():
                        classic_bikes += count
                    else:
                        # If we can't determine type, count as classic
                        classic_bikes += count
            
            # Get station name from station information if available
            station_info = self._get_station_information()
            station_name = station_id
            if station_info and station_id in station_info:
                station_name = station_info[station_id].get("name", station_id)
            
            # Determine status color based on electric bike availability
            status_color = self._get_status_color(electric_bikes)
            
            return {
                "station_id": station_id,
                "station_name": station_name,
                "num_bikes_available": num_bikes_available,
                "electric_bikes": electric_bikes,
                "classic_bikes": classic_bikes,
                "is_renting": is_renting,
                "status_color": status_color,
                "total_docks": station_data.get("num_docks_available", 0) + num_bikes_available,
                "num_docks_available": station_data.get("num_docks_available", 0),
            }
        except Exception as e:
            logger.error(f"Error parsing station data: {e}")
            return None
    
    def fetch_station_status(self) -> Optional[Dict[str, any]]:
        """
        Fetch current bike availability for the first configured station (backward compatibility).
        
        Returns:
            Dictionary with bike availability data for first station, or None if fetch failed.
        """
        if not self.station_ids:
            return None
        
        # For backward compatibility, return data for first station
        results = self.fetch_multiple_stations()
        if results and len(results) > 0:
            return results[0]
        return None
    
    def fetch_multiple_stations(self) -> List[Dict[str, any]]:
        """
        Fetch current bike availability for all configured stations.
        
        Returns:
            List of dictionaries with bike availability data for each station
        """
        if not self.station_ids:
            return []
        
        try:
            response = requests.get(STATION_STATUS_URL, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Build a map of station_id -> station_data for quick lookup
            stations_map = {}
            stations = data.get("data", {}).get("stations", [])
            for station in stations:
                station_id = station.get("station_id")
                if station_id:
                    stations_map[station_id] = station
            
            # Fetch data for each configured station
            results = []
            for station_id in self.station_ids:
                if station_id in stations_map:
                    parsed = self._parse_station_status(stations_map[station_id])
                    if parsed:
                        results.append(parsed)
                else:
                    logger.warning(f"Station {station_id} not found in GBFS feed")
            
            return results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch Bay Wheels data: {e}")
            return []
        except (KeyError, ValueError) as e:
            logger.error(f"Unexpected response format from Bay Wheels GBFS: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching Bay Wheels data: {e}")
            return []
    
    def get_aggregate_stats(self) -> Dict[str, any]:
        """
        Get aggregate statistics across all tracked stations.
        
        Returns:
            Dictionary with aggregate stats:
            {
                "total_electric": int,
                "total_classic": int,
                "total_bikes": int,
                "station_count": int,
                "stations": List[Dict]  # Individual station data
            }
        """
        stations = self.fetch_multiple_stations()
        
        total_electric = sum(s.get("electric_bikes", 0) for s in stations)
        total_classic = sum(s.get("classic_bikes", 0) for s in stations)
        total_bikes = sum(s.get("num_bikes_available", 0) for s in stations)
        
        return {
            "total_electric": total_electric,
            "total_classic": total_classic,
            "total_bikes": total_bikes,
            "station_count": len(stations),
            "stations": stations,
        }
    
    def get_best_station(self) -> Optional[Dict[str, any]]:
        """
        Find the station with the most electric bikes available.
        
        Returns:
            Dictionary with station data for best station, or None if no stations
        """
        stations = self.fetch_multiple_stations()
        
        if not stations:
            return None
        
        # Find station with most electric bikes
        best = max(stations, key=lambda s: s.get("electric_bikes", 0))
        return best
    
    @classmethod
    def find_stations_near_location(
        cls, 
        lat: float, 
        lng: float, 
        radius_km: float = 2.0, 
        limit: int = 10
    ) -> List[Dict[str, any]]:
        """
        Find stations near a given location.
        
        Args:
            lat: Latitude
            lng: Longitude
            radius_km: Search radius in kilometers (default 2.0)
            limit: Maximum number of results (default 10)
            
        Returns:
            List of station dictionaries with distance information, sorted by distance
        """
        station_info = cls._get_station_information()
        if not station_info:
            logger.warning("Station information not available for location search")
            return []
        
        # Calculate distance to each station
        stations_with_distance = []
        for station_id, info in station_info.items():
            station_lat = info.get("lat")
            station_lon = info.get("lon")
            
            if station_lat is None or station_lon is None:
                continue
            
            distance = _haversine_distance(lat, lng, station_lat, station_lon)
            
            if distance <= radius_km:
                stations_with_distance.append({
                    "station_id": station_id,
                    "name": info.get("name", station_id),
                    "lat": station_lat,
                    "lon": station_lon,
                    "address": info.get("address", ""),
                    "capacity": info.get("capacity", 0),
                    "distance_km": round(distance, 2),
                })
        
        # Sort by distance and limit results
        stations_with_distance.sort(key=lambda x: x["distance_km"])
        return stations_with_distance[:limit]
    
    def _get_status_color(self, electric_bikes: int) -> str:
        """
        Determine status color based on electric bike count.
        
        Args:
            electric_bikes: Number of electric bikes available
            
        Returns:
            Color name: "red" (< 2), "yellow" (2-5), or "green" (> 5)
        """
        if electric_bikes < 2:
            return "red"
        elif electric_bikes > 5:
            return "green"
        else:
            return "yellow"


def get_baywheels_source() -> Optional[BayWheelsSource]:
    """Get configured Bay Wheels source instance."""
    if not Config.BAYWHEELS_ENABLED:
        logger.debug("Bay Wheels integration not enabled")
        return None
    
    # Get station IDs (supports both single and multiple)
    station_ids = Config.BAYWHEELS_STATION_IDS
    
    if not station_ids:
        logger.warning("Bay Wheels station IDs not configured")
        return None
    
    return BayWheelsSource(station_ids=station_ids)

