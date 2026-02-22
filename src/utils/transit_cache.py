"""Regional Transit Cache Service for 511.org API.

This module provides a singleton cache service that fetches regional transit data
from 511.org once every 90 seconds and caches it in memory. This reduces API calls
from potentially 100+ per hour to ~40 per hour, staying well within the 60/hour limit.

The cache fetches ALL Bay Area transit data using agency=RG, then serves filtered
data to specific transit sources (Muni, BART, etc.) from the cache.
"""

import logging
import requests
import json
import threading
import time
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TransitCache:
    """Singleton service that caches regional transit data from 511.org."""
    
    _instance: Optional["TransitCache"] = None
    _lock = threading.Lock()
    
    # API configuration
    API_BASE_URL = "http://api.511.org/transit/StopMonitoring"
    REGIONAL_AGENCY = "SF"  # SF Muni agency (RG regional feed is empty, use SF directly)
    
    # Cache configuration (defaults, can be overridden)
    DEFAULT_REFRESH_INTERVAL = 90  # seconds
    STALE_WARNING_THRESHOLD = 300  # 5 minutes - warn if cache is this old
    
    def __new__(cls) -> "TransitCache":
        """Singleton pattern to ensure only one cache instance exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the transit cache (only runs once due to singleton)."""
        if self._initialized:
            return
        
        # Thread safety
        self._data_lock = threading.RLock()
        
        # Cache storage
        self._raw_data: Optional[Dict[str, Any]] = None
        self._last_refresh: float = 0
        self._last_success: float = 0
        self._refresh_count: int = 0
        self._error_count: int = 0
        self._cache_hits: int = 0
        
        # Parsed cache by agency and stop
        self._stops_by_agency: Dict[str, Dict[str, List[Dict]]] = {}  # agency -> stop_code -> [visits]
        
        # Configuration
        self._api_key: Optional[str] = None
        self._refresh_interval: int = self.DEFAULT_REFRESH_INTERVAL
        self._enabled: bool = False
        
        # Background refresh thread
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._initialized = True
        logger.info("TransitCache initialized (not started)")
    
    def configure(self, api_key: str, refresh_interval: int = DEFAULT_REFRESH_INTERVAL, enabled: bool = True):
        """
        Configure the cache with API key and settings.
        
        Args:
            api_key: 511.org API key
            refresh_interval: Refresh interval in seconds (default 90)
            enabled: Whether cache is enabled (default True)
        """
        with self._data_lock:
            self._api_key = api_key
            self._refresh_interval = refresh_interval
            self._enabled = enabled
            logger.info(f"TransitCache configured: enabled={enabled}, interval={refresh_interval}s")
    
    def start(self):
        """Start the background refresh thread."""
        if not self._enabled:
            logger.warning("TransitCache not started - disabled in configuration")
            return
        
        if not self._api_key:
            logger.error("TransitCache not started - no API key configured")
            return
        
        with self._lock:
            if self._refresh_thread is not None and self._refresh_thread.is_alive():
                logger.warning("TransitCache refresh thread already running")
                return
            
            logger.info(f"Starting TransitCache refresh thread (interval: {self._refresh_interval}s)")
            self._stop_event.clear()
            self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True, name="TransitCache")
            self._refresh_thread.start()
            
            # Do an immediate first refresh
            self._refresh_data()
    
    def stop(self):
        """Stop the background refresh thread."""
        logger.info("Stopping TransitCache refresh thread")
        self._stop_event.set()
        if self._refresh_thread:
            self._refresh_thread.join(timeout=5)
    
    def _refresh_loop(self):
        """Background thread that refreshes cache periodically."""
        logger.info("TransitCache refresh loop started")
        
        while not self._stop_event.is_set():
            try:
                self._refresh_data()
            except Exception as e:
                logger.error(f"Error in TransitCache refresh loop: {e}", exc_info=True)
            
            # Wait for next refresh interval (or until stop event)
            self._stop_event.wait(self._refresh_interval)
        
        logger.info("TransitCache refresh loop stopped")
    
    def _refresh_data(self):
        """Fetch fresh regional transit data from 511.org API."""
        if not self._api_key:
            logger.error("Cannot refresh TransitCache - no API key")
            return
        
        start_time = time.time()
        
        try:
            params = {
                "api_key": self._api_key,
                "agency": self.REGIONAL_AGENCY,
                "format": "json"
            }
            
            logger.debug(f"Fetching regional transit data from 511.org (agency={self.REGIONAL_AGENCY})")
            response = requests.get(self.API_BASE_URL, params=params, timeout=15)
            response.raise_for_status()
            
            # Handle BOM if present
            content = response.text
            if content.startswith('\ufeff'):
                content = content[1:]
            
            data = json.loads(content)
            
            # Parse and index the data
            self._parse_and_index(data)
            
            # Update cache metadata
            with self._data_lock:
                self._raw_data = data
                self._last_refresh = time.time()
                self._last_success = time.time()
                self._refresh_count += 1
            
            elapsed = time.time() - start_time
            logger.info(f"TransitCache refreshed successfully in {elapsed:.2f}s (refresh #{self._refresh_count})")
            
        except requests.exceptions.HTTPError as e:
            with self._data_lock:
                self._error_count += 1
            
            if e.response.status_code == 429:
                logger.error(f"Rate limited by 511.org API! This shouldn't happen with regional caching. "
                           f"Refresh interval may be too short ({self._refresh_interval}s)")
            else:
                logger.error(f"HTTP error fetching regional transit data: {e}")
                
        except requests.exceptions.RequestException as e:
            with self._data_lock:
                self._error_count += 1
            logger.error(f"Network error fetching regional transit data: {e}")
            
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            with self._data_lock:
                self._error_count += 1
            logger.error(f"Error parsing 511.org regional response: {e}", exc_info=True)
            
        except Exception as e:
            with self._data_lock:
                self._error_count += 1
            logger.error(f"Unexpected error refreshing TransitCache: {e}", exc_info=True)
    
    def _parse_and_index(self, data: Dict[str, Any]):
        """
        Parse regional transit data and index by agency and stop code.
        
        Args:
            data: Raw JSON response from 511.org StopMonitoring API
        """
        try:
            # Navigate to monitored stop visits
            service_delivery = data.get("ServiceDelivery", {})
            stop_monitoring = service_delivery.get("StopMonitoringDelivery", {})
            
            # Handle both list and single object responses
            if isinstance(stop_monitoring, list):
                stop_monitoring = stop_monitoring[0] if stop_monitoring else {}
            
            monitored_visits = stop_monitoring.get("MonitoredStopVisit", [])
            
            # Index by agency and stop code
            indexed: Dict[str, Dict[str, List[Dict]]] = {}
            
            for visit in monitored_visits:
                try:
                    journey = visit.get("MonitoredVehicleJourney", {})
                    monitored_call = journey.get("MonitoredCall", {})
                    
                    # Extract agency from OperatorRef or other fields
                    # Format is typically like "SF" for Muni, "BA" for BART, etc.
                    operator_ref = journey.get("OperatorRef", "")
                    if isinstance(operator_ref, list):
                        operator_ref = operator_ref[0] if operator_ref else ""
                    
                    # Extract stop code from StopPointRef
                    stop_ref = monitored_call.get("StopPointRef", "")
                    if isinstance(stop_ref, list):
                        stop_ref = stop_ref[0] if stop_ref else ""
                    
                    # Parse stop code (format is usually "AGENCY_STOPCODE" like "SF_15210")
                    if "_" in stop_ref:
                        agency, stop_code = stop_ref.split("_", 1)
                    else:
                        agency = operator_ref or "UNKNOWN"
                        stop_code = stop_ref
                    
                    # Index the visit
                    if agency not in indexed:
                        indexed[agency] = {}
                    if stop_code not in indexed[agency]:
                        indexed[agency][stop_code] = []
                    
                    indexed[agency][stop_code].append(visit)
                    
                except Exception as e:
                    logger.debug(f"Error indexing transit visit: {e}")
                    continue
            
            # Update indexed cache
            with self._data_lock:
                self._stops_by_agency = indexed
            
            # Log statistics
            total_agencies = len(indexed)
            total_stops = sum(len(stops) for stops in indexed.values())
            total_visits = sum(sum(len(visits) for visits in stops.values()) for stops in indexed.values())
            logger.debug(f"Indexed {total_visits} visits across {total_stops} stops from {total_agencies} agencies")
            
        except Exception as e:
            logger.error(f"Error parsing and indexing regional transit data: {e}", exc_info=True)
    
    def get_stops_data(self, agency: str, stop_codes: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get cached transit data for specific stops from a specific agency.
        
        Args:
            agency: Agency code (e.g., "SF" for Muni)
            stop_codes: List of stop codes to retrieve
            
        Returns:
            Dictionary mapping stop_code -> list of MonitoredStopVisit dicts
        """
        with self._data_lock:
            self._cache_hits += 1
            
            # Check cache age and warn if stale
            age = time.time() - self._last_success if self._last_success > 0 else float('inf')
            if age > self.STALE_WARNING_THRESHOLD:
                logger.warning(f"TransitCache is stale (age: {age:.0f}s). Data may be outdated.")
            
            # Get agency data
            agency_data = self._stops_by_agency.get(agency, {})
            
            # Filter by requested stop codes
            result = {}
            for stop_code in stop_codes:
                visits = agency_data.get(stop_code, [])
                result[stop_code] = visits
            
            return result
    
    def get_all_stops_for_agency(self, agency: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all cached transit data for an agency.
        
        Args:
            agency: Agency code (e.g., "SF" for Muni)
            
        Returns:
            Dictionary mapping stop_code -> list of MonitoredStopVisit dicts
        """
        with self._data_lock:
            return self._stops_by_agency.get(agency, {}).copy()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get cache status and statistics.
        
        Returns:
            Dictionary with cache status information
        """
        with self._data_lock:
            age = time.time() - self._last_success if self._last_success > 0 else None
            is_stale = age is not None and age > self.STALE_WARNING_THRESHOLD
            
            agencies = list(self._stops_by_agency.keys())
            total_stops = sum(len(stops) for stops in self._stops_by_agency.values())
            
            return {
                "enabled": self._enabled,
                "refresh_interval": self._refresh_interval,
                "last_refresh": self._last_refresh,
                "last_success": self._last_success,
                "cache_age_seconds": age,
                "is_stale": is_stale,
                "refresh_count": self._refresh_count,
                "error_count": self._error_count,
                "cache_hits": self._cache_hits,
                "agencies_cached": agencies,
                "total_stops_cached": total_stops,
                "thread_alive": self._refresh_thread.is_alive() if self._refresh_thread else False,
            }
    
    def is_ready(self) -> bool:
        """
        Check if cache has been successfully populated at least once.
        
        Returns:
            True if cache has valid data, False otherwise
        """
        with self._data_lock:
            return self._last_success > 0


# Global singleton instance getter
_cache_instance: Optional[TransitCache] = None


def get_transit_cache() -> TransitCache:
    """Get the singleton TransitCache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = TransitCache()
    return _cache_instance

