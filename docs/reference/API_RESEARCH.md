# API Research Documentation

This document contains detailed research findings for all APIs that will be integrated into the FiestaBoard display service.

## 1. Board Read/Write API

### Authentication
- **API Key Location**: Enable Read/Write API in the API tab on [web.vestaboard.com](https://web.vestaboard.com)
- **Header Name**: `X-Vestaboard-Read-Write-Key` (official board API header)
- **Key Type**: Single Read/Write API key (not separate key/secret)
- **Key Management**: 
  - Only one key allowed at a time
  - Can be disabled or regenerated at any time
  - Key is specific to your board

### Endpoints

#### Base URL
- `https://rw.vestaboard.com/`

#### Read Current Message
- **Method**: `GET`
- **Headers**: 
  - `X-Vestaboard-Read-Write-Key: <your-api-key>`
- **Response**: Current message displayed on the board

#### Send Message
- **Method**: `POST`
- **Headers**: 
  - `X-Vestaboard-Read-Write-Key: <your-api-key>`
  - `Content-Type: application/json`
- **Request Body Options**:
  1. **Plain Text**:
     ```json
     {
       "text": "Your message here"
     }
     ```
  2. **Character Array** (6x22 grid):
     ```json
     {
       "characters": [
         [0, 0, 0, ...],  // Row 1 (22 elements)
         [0, 0, 0, ...],  // Row 2 (22 elements)
         // ... 6 rows total
       ]
     }
     ```

### Rate Limiting
- **Limit**: One message every 15 seconds
- **Behavior**: Messages sent more frequently may be dropped
- **Recommendation**: Implement minimum 15-second delay between sends

### Message Format
- **Grid Size**: 6 rows × 22 columns (132 characters total)
- **Character Encoding**: 
  - Plain text is automatically converted to character codes
  - For precise control, use character array format
  - Character codes are numeric (0-63+ for different characters/symbols)
- **FBML**: Board Markup Language available for richer formatting
- **Character Codes**: Reference table available in board documentation

### Python Libraries
- **`vesta`** library available on PyPI: `pip install vesta`
- Provides client classes for easier integration
- Handles character encoding and message formatting

### Important Notes
- API does not accept blank messages
- Messages are sent immediately when API is called
- No queuing system - last message sent overwrites previous

---

## 2. Weather APIs

### Option A: OpenWeatherMap

#### API Access
- **Sign Up**: [openweathermap.org](https://openweathermap.org/)
- **Free Tier**: 
  - 1,000 calls per day
  - 60 calls per minute
  - Current weather data
  - 5-day/3-hour forecast
  - Historical data (limited)

#### Endpoints

**Current Weather**
```
GET https://api.openweathermap.org/data/2.5/weather
```

**Parameters**:
- `q`: City name (e.g., "San Francisco, CA")
- `appid`: API key (required)
- `units`: `imperial` (Fahrenheit) or `metric` (Celsius)
- `lat`/`lon`: Alternative to city name (latitude/longitude)

**Example Request**:
```
GET https://api.openweathermap.org/data/2.5/weather?q=San%20Francisco,CA&appid=YOUR_API_KEY&units=imperial
```

**Response Fields** (relevant):
- `main.temp`: Temperature
- `main.feels_like`: Feels like temperature
- `weather[0].main`: Weather condition (e.g., "Clear", "Clouds")
- `weather[0].description`: Detailed description
- `main.humidity`: Humidity percentage
- `wind.speed`: Wind speed

#### Rate Limits
- **Free Tier**: 60 calls/minute, 1,000 calls/day
- **Recommendation**: For 5-minute refresh, ~288 calls/day (well within limit)

### Option B: WeatherAPI.com

#### API Access
- **Sign Up**: [weatherapi.com](https://www.weatherapi.com/)
- **Free Tier**:
  - 1 million calls per month
  - No credit card required
  - Current weather + 3-day forecast

#### Endpoints

**Current Weather**
```
GET http://api.weatherapi.com/v1/current.json
```

**Parameters**:
- `key`: API key (required)
- `q`: Location (city name, lat/lon, or IP)
- `aqi`: Air quality index (yes/no)

**Example Request**:
```
GET http://api.weatherapi.com/v1/current.json?key=YOUR_API_KEY&q=San%20Francisco&aqi=no
```

**Response Fields** (relevant):
- `current.temp_f`: Temperature in Fahrenheit
- `current.feelslike_f`: Feels like temperature
- `current.condition.text`: Weather condition description
- `current.humidity`: Humidity percentage
- `current.wind_mph`: Wind speed in mph

#### Rate Limits
- **Free Tier**: 1 million calls/month (~33,333/day)
- **Recommendation**: Very generous limits, suitable for frequent updates

### Recommendation
- **WeatherAPI.com** is recommended for:
  - Higher free tier limits (1M/month vs 1K/day)
  - Simpler API structure
  - No credit card required
- **OpenWeatherMap** alternative if:
  - You need historical data
  - You prefer more detailed forecasts

---

## 3. Baywheels GBFS API

### Overview
- **Standard**: General Bikeshare Feed Specification (GBFS) v3.1-RC2
- **Format**: JSON
- **Access**: Public, no API key required
- **Update Frequency**: Real-time (typically updated every 30-60 seconds)

### Base URL
- **Discovery Endpoint**: `https://gbfs.baywheels.com/gbfs/gbfs.json`
- This file contains links to all other data feeds

### Key Endpoints

#### 1. System Information
- **File**: `system_information.json`
- **Contains**: 
  - System name, operator, location
  - Timezone
  - Contact information
  - System ID

#### 2. Station Information
- **File**: `station_information.json`
- **Contains**:
  - Station IDs
  - Station names
  - Latitude/longitude coordinates
  - Station capacity
  - Address (if available)

**Example Structure**:
```json
{
  "last_updated": 1234567890,
  "ttl": 3600,
  "data": {
    "stations": [
      {
        "station_id": "123",
        "name": "Market St & 5th St",
        "lat": 37.7749,
        "lon": -122.4194,
        "capacity": 15,
        "address": "123 Market St"
      }
    ]
  }
}
```

#### 3. Station Status
- **File**: `station_status.json`
- **Contains**:
  - Real-time bike availability
  - Available docks
  - Station operational status
  - Last reported time

**Example Structure**:
```json
{
  "last_updated": 1234567890,
  "ttl": 60,
  "data": {
    "stations": [
      {
        "station_id": "123",
        "num_bikes_available": 5,
        "num_docks_available": 10,
        "is_renting": true,
        "is_returning": true,
        "last_reported": 1234567890
      }
    ]
  }
}
```

### Implementation Strategy

1. **Fetch Discovery File**: Get `gbfs.json` to find feed URLs
2. **Get Station Information**: Fetch all station locations
3. **Get Station Status**: Fetch real-time availability
4. **Calculate Nearest Station**: 
   - Use user's location (from config)
   - Calculate distance using Haversine formula
   - Find closest station with available bikes
5. **Format Display**: Show station name, bikes available, docks available, distance

### Data Refresh
- **TTL (Time To Live)**: Each feed includes a `ttl` field indicating cache duration
- **Last Updated**: Timestamp of last data update
- **Recommendation**: Refresh every 5 minutes (well within typical TTL of 60 seconds)

### Notes
- No authentication required
- CORS may be enabled (check if calling from browser)
- Some stations may be temporarily unavailable
- Station IDs are consistent across feeds

---

## 4. Waymo API (Unofficial)

### Overview
- **Repository**: [puravparab/waymo-api](https://github.com/puravparab/waymo-api/)
- **Status**: Unofficial API (not maintained by Waymo)
- **Language**: Python library available
- **Reliability**: May have limitations or break if Waymo changes their internal API

### Research Needed
Since this is an unofficial API, we need to:
1. Check the GitHub repository for:
   - Authentication requirements
   - Available endpoints
   - Rate limits
   - Example usage
   - Current maintenance status
2. Verify if it still works (may be outdated)
3. Understand data format and pricing structure

### Potential Endpoints (to verify)
- Price estimation for routes
- Wait time estimates
- Service availability

### Considerations
- **Unofficial**: May stop working at any time
- **Rate Limiting**: Unknown limits
- **Legal**: Ensure compliance with Waymo's terms of service
- **Fallback**: Implement graceful degradation if API fails

### Recommendation
- Research the GitHub repo first
- Test API availability before implementing
- Add robust error handling
- Consider making this feature optional/disabled by default

---

## 5. Date/Time Display

### Implementation
- **Library**: Python's built-in `datetime` module
- **Timezone**: Use `pytz` or `zoneinfo` (Python 3.9+) for timezone handling
- **Format**: Configurable via config file

### No External API Required
- Uses system time or NTP-synced time
- No rate limits
- No authentication needed

---

## Summary & Recommendations

### Priority Implementation Order

1. **Board API** (Required)
   - Core functionality
   - Simple authentication
   - Rate limit: 15 seconds between messages

2. **Date/Time** (Required)
   - No external dependencies
   - Simple implementation

3. **Weather API** (Required for MVP)
   - **Recommendation**: WeatherAPI.com (better free tier)
   - Simple integration
   - Reliable service

4. **Baywheels GBFS** (Phase 3)
   - Public API, no authentication
   - Well-documented standard
   - Real-time data

5. **Waymo API** (Phase 4)
   - Requires research
   - Unofficial - may be unreliable
   - Implement with caution

### Configuration Requirements

All APIs will need configuration in `config.yaml`:

```yaml
board:
  read_write_key: ${FB_READ_WRITE_KEY}  # From .env

weather:
  provider: "weatherapi"  # or "openweathermap"
  api_key: ${WEATHER_API_KEY}
  location: "San Francisco, CA"
  units: "imperial"

baywheels:
  enabled: false  # Phase 3
  user_latitude: 37.7749
  user_longitude: -122.4194
  max_distance_miles: 2.0

waymo:
  enabled: false  # Phase 4
  # TBD after research
```

### Rate Limiting Strategy

| Service | Limit | Our Usage | Status |
|---------|-------|-----------|--------|
| Board | 1 msg/15s | Every 5+ min | ✅ Safe |
| WeatherAPI | 1M/month | ~288/day | ✅ Safe |
| OpenWeatherMap | 1K/day | ~288/day | ✅ Safe |
| Baywheels GBFS | None | Every 5 min | ✅ Safe |
| Waymo | Unknown | TBD | ⚠️ Research needed |

### Next Steps

1. ✅ Research complete for Board, Weather, Baywheels
2. ⏳ Research Waymo API GitHub repo in detail
3. ⏳ Test Board API with actual credentials
4. ⏳ Verify Baywheels GBFS endpoint accessibility
5. ⏳ Choose weather provider and get API key

---

## References

- [Vestaboard Read/Write API Docs](https://docs.vestaboard.com/docs/read-write-api/introduction)
- [GBFS Specification](https://github.com/MobilityData/gbfs/blob/master/gbfs.md)
- [Baywheels System Data](https://www.lyft.com/bikes/bay-wheels/system-data)
- [OpenWeatherMap API](https://openweathermap.org/api)
- [WeatherAPI.com](https://www.weatherapi.com/)
- [Waymo API (Unofficial)](https://github.com/puravparab/waymo-api/)

