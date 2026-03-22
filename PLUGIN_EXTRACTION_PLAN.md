# Plugin Extraction Plan

This document outlines the plan to extract plugins that require external API keys into
their own public repositories under the [FiestaBoard](https://github.com/FiestaBoard)
GitHub organization.

## Why Extract?

Plugins that depend on paid or authenticated APIs have different maintenance needs:

- API providers change their endpoints, authentication schemes, and rate limits.
- Users must manage their own API keys and billing.
- Keeping these plugins in their own repositories makes it easier for contributors
  to submit fixes without touching the core project.
- Extracted plugins serve as real-world examples of how to build an external
  FiestaBoard plugin.

## Naming Convention

All extracted plugins **must** follow the naming convention:

```
fiestaboard-plugin--{name}
```

For example, the Weather plugin becomes `fiestaboard-plugin--weather`.

## Plugins to Extract

The plugins below require an external API key or authenticated access. They are
candidates for extraction into standalone repositories.

### Required API Key

| Current Plugin | Target Repository | API Provider |
|---|---|---|
| `weather` | `fiestaboard-plugin--weather` | WeatherAPI / OpenWeatherMap |
| `traffic` | `fiestaboard-plugin--traffic` | Google Routes API |
| `muni` | `fiestaboard-plugin--muni` | 511.org |

### Free-Tier API Key

| Current Plugin | Target Repository | API Provider |
|---|---|---|
| `home_assistant` | `fiestaboard-plugin--home-assistant` | Home Assistant (self-hosted) |
| `air_fog` | `fiestaboard-plugin--air-fog` | PurpleAir / OpenWeatherMap |

### Optional API Key (Enhanced With)

| Current Plugin | Target Repository | API Provider |
|---|---|---|
| `last_fm` | `fiestaboard-plugin--last-fm` | Last.fm |
| `wsdot` | `fiestaboard-plugin--wsdot` | WSDOT |
| `stocks` | `fiestaboard-plugin--stocks` | Finnhub |
| `sports_scores` | `fiestaboard-plugin--sports-scores` | TheSportsDB |
| `nearby_aircraft` | `fiestaboard-plugin--nearby-aircraft` | OpenSky Network |

## Extraction Steps (per plugin)

1. Create the new public repository `fiestaboard-plugin--{name}` in the FiestaBoard
   organization.
2. Copy the plugin directory contents into the new repository root.
3. Add the repository URL to `plugin-registry.json` in this repository.
4. Update the plugin's `manifest.json` `repository` field to point to the new repo.
5. Keep the built-in copy in this repository until the next major release so that
   existing users are not broken.
6. Mark the built-in copy as deprecated with a note in its `README.md`.
7. After the deprecation period, remove the built-in copy from this repository.

## Timeline

Extraction is not urgent. The current built-in plugins continue to work. This plan
will be executed incrementally, starting with the plugins that have the most active
external API dependencies (weather, traffic, home_assistant).
