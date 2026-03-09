# Allergy & Health Plugin

Display allergy levels (pollen counts), air quality indices, and environmental health risk indicators for your area.

## Features

- **Pollen Counts**: Grass, tree (birch + alder), and weed (ragweed) pollen levels in grains/m³
- **Air Quality**: US AQI, European AQI, PM2.5, and PM10 measurements
- **Health Risk Indicators**: Flu, cough, and respiratory risk scores on a 0–12 scale derived from environmental factors
- **Allergy Risk Level**: Overall classification (LOW / MODERATE / HIGH / VERY HIGH) with color coding

## Data Source

This plugin uses the [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api), which is **free** and requires **no API key**.

Pollen data availability varies by region — it is best supported in Europe and North America.

## Variables

| Variable | Description | Example |
|---|---|---|
| `grass_pollen` | Grass pollen (grains/m³) | `12` |
| `tree_pollen` | Tree pollen — birch + alder (grains/m³) | `65` |
| `weed_pollen` | Weed pollen — ragweed (grains/m³) | `8` |
| `aqi` | US Air Quality Index | `42` |
| `european_aqi` | European AQI | `30` |
| `pm25` | PM2.5 concentration (µg/m³) | `8.5` |
| `pm10` | PM10 concentration (µg/m³) | `15.0` |
| `allergy_risk` | Overall allergy risk level | `MODERATE` |
| `allergy_risk_color` | Board color code for allergy risk | `{65}` |
| `respiratory_risk` | Respiratory risk score (0–12) | `2.4` |
| `flu_risk` | Flu risk score (0–12) | `1.2` |
| `cough_risk` | Cough risk score (0–12) | `1.7` |
| `formatted` | Pre-formatted summary string | `ALLERGY: MODERATE` |

## Configuration

| Setting | Type | Default | Description |
|---|---|---|---|
| `latitude` | number | 37.7749 | Location latitude |
| `longitude` | number | -122.4194 | Location longitude |
| `refresh_seconds` | integer | 600 | Data refresh interval in seconds |

## Health Risk Scores

The 0–12 health risk scores are derived from environmental air quality and pollen data:

- **Respiratory Risk**: Weighted combination of AQI (0–6 pts), PM2.5 (0–3 pts), and total pollen (0–3 pts)
- **Flu Risk**: Weighted combination of AQI (0–6 pts), PM2.5 (0–3 pts), and PM10 (0–3 pts)
- **Cough Risk**: Weighted combination of AQI (0–4 pts), PM2.5 (0–4 pts), and total pollen (0–4 pts)

Higher scores indicate greater environmental risk factors for the respective health conditions.

## Example Display

```
  ALLERGY & HEALTH
     PPM       0-12
GRASS:   0 FLU:  1.2
TREES:  65 COUGH:1.7
WEEDS:   0 RESP: 2.4
AQI:   42 EAQI:  30
```
