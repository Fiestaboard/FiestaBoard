# Analytics & Telemetry Plan

## Overview

This document proposes a privacy-first, opt-in analytics system for FiestaBoard. The goal is to understand how FiestaBoard is being used — which plugins are popular, what kinds of content are displayed, how often boards update, and what errors occur — so that development efforts can be prioritized while respecting users' privacy and the constraints of running on a local network.

**Key Principle:** Analytics must be **opt-in with a default of opt-out**. No data is ever collected or transmitted unless the user explicitly enables it.

**Key Privacy Rule:** We **never** collect message content — no actual text, words, or readable messages. We may collect anonymous aggregate characteristics of what's displayed (color tile counts, symbol counts, blank space counts) to understand *what kind* of content is shown, but never the content itself.

---

## How Home Assistant Does It (Reference Model)

Home Assistant is the gold standard for opt-in analytics in the self-hosted/local-network space. Their approach:

| Aspect | Home Assistant's Approach |
|---|---|
| **Default** | Opt-out (disabled by default) |
| **Opt-in location** | Onboarding flow + Settings > System > Analytics |
| **Granularity** | Users choose categories: Basic, Usage, Statistics, Diagnostics |
| **What's collected** | Anonymous installation ID, version, region, integration counts, entity counts — never entity names, states, or personal data |
| **Transmission** | 15 min after startup, then once every 24 hours |
| **Anonymization** | Unique non-identifying installation UUID |
| **Storage** | Cloudflare KV store, 60-day retention max |
| **Transparency** | Exact payload is logged locally; users can inspect what is sent |
| **Public data** | Only aggregated stats published (e.g., most popular integrations) |
| **Adoption** | Less than 25% of users opt in — respecting user choice |

**Key Takeaways for FiestaBoard:**
- Granular opt-in categories give users control
- Logging the exact payload locally builds trust
- Sending data infrequently (once/day) minimizes network impact
- Anonymous UUIDs prevent identification
- Short retention periods limit data exposure

---

## Three Workstreams

This effort spans three separate areas of work:

| # | Workstream | Repo | Description |
|---|---|---|---|
| **1** | **FiestaBoard App** | `Fiestaboard/FiestaBoard` | Collect metrics locally, opt-in UI, daily payload sender |
| **2** | **Cloud Ingest Service** | `Fiestaboard/analytics-ingest` (new repo) | AWS-hosted API to receive + store JSON payloads |
| **3** | **Public Transparency Site** | `Fiestaboard/analytics-public` (new repo) | Static site showing aggregated anonymous data publicly |

```
┌─────────────────────────────┐         ┌──────────────────────────────┐      ┌──────────────────────┐
│  Workstream 1               │         │  Workstream 2                │      │  Workstream 3        │
│  User's Local Network       │         │  AWS Cloud Infrastructure    │      │  Public Site         │
│                             │         │                              │      │                      │
│  ┌───────────────────────┐  │  HTTPS  │  ┌────────────────────────┐ │      │  ┌────────────────┐  │
│  │  FiestaBoard App      │──│────────>│──│  API Gateway + Lambda  │ │      │  │  Static Site   │  │
│  │  (Python/FastAPI)     │  │ 1x/day  │  │  (ingest endpoint)     │ │      │  │  (S3 + CF)     │  │
│  │                       │  │         │  └──────────┬─────────────┘ │      │  │                │  │
│  │  - Collects metrics   │  │         │             │               │      │  │  Aggregated    │  │
│  │  - Opt-in UI toggle   │  │         │  ┌──────────▼─────────────┐ │ JSON │  │  charts &      │  │
│  │  - Logs payload       │  │         │  │  DynamoDB              │─│─────>│  │  stats         │  │
│  │  - Sends if opted in  │  │         │  │  (telemetry storage)   │ │      │  │                │  │
│  └───────────────────────┘  │         │  └──────────┬─────────────┘ │      │  │  analytics.    │  │
│                             │         │             │               │      │  │  fiestaboard.  │  │
└─────────────────────────────┘         │  ┌──────────▼─────────────┐ │      │  │  com           │  │
                                        │  │  Lambda (aggregation)  │ │      │  └────────────────┘  │
                                        │  │  (daily cron job)      │ │      │                      │
                                        │  └────────────────────────┘ │      └──────────────────────┘
                                        └──────────────────────────────┘
```

---

## Workstream 1: FiestaBoard App Changes

### Architecture: Lightweight Outbound Telemetry

Since FiestaBoard runs on users' local networks (often Raspberry Pi), we should **not** ask users to host an analytics server locally. Instead:

1. **FiestaBoard backend** collects anonymous usage metrics locally (in memory, never persisted to disk except the config toggle)
2. **On a schedule** (once per day), if the user has opted in, a small JSON payload is sent to the project-owned AWS endpoint
3. **Transparency**: the exact payload is logged at INFO level before sending so users can inspect it

### Why Not Self-Hosted Analytics on the User's Pi?

- Grafana + Prometheus/InfluxDB are too heavy for a Raspberry Pi already running FiestaBoard
- Users shouldn't have to manage an analytics stack
- The project needs aggregated data across all installations, not per-user dashboards
- Local-only analytics wouldn't help the maintainers understand usage patterns

---

## Comprehensive Data Collection Inventory

Everything below is derived from what the FiestaBoard codebase actually tracks today. This is the **complete list** of what would be collected — nothing else.

### Level 1: Basic Analytics

Minimal system information. No usage patterns.

| Data Point | Example Value | Source | Purpose |
|---|---|---|---|
| Anonymous installation UUID | `"a1b2c3d4-e5f6-..."` | Generated once on opt-in | Count unique installations |
| FiestaBoard version | `"1.32.44"` | Package version | Track update adoption |
| Platform / architecture | `"linux/arm64"` | `platform` module | Understand deployment targets (Pi vs x86) |
| Python version | `"3.11.2"` | `sys.version` | Know minimum version to support |
| Board API mode | `"local"` or `"cloud"` | `config.json → board.api_mode` | Understand local vs cloud board usage |
| Output target | `"board"`, `"ui"`, or `"both"` | `config.json → general.output_target` | Know how people use FiestaBoard |
| Uptime since last restart (hours) | `168` | Process start time | Gauge reliability and restart frequency |

### Level 2: Usage Analytics

How FiestaBoard is being used — still anonymous, no content.

#### Plugin Analytics

| Data Point | Example Value | Source | Purpose |
|---|---|---|---|
| Enabled plugin names | `["weather", "stocks", "muni"]` | `PluginRegistry._enabled` | Which plugins are popular |
| Plugin states | `{"weather": "active", "stocks": "error", "muni": "setup"}` | `PluginResult.available` + `PluginResult.error` | Understand plugin health |
| Plugin error messages (generic) | `{"stocks": "API timeout"}` | `PluginResult.error` | Surface common plugin failures (for maintainers — see note below) |
| Plugin load errors | `{"my_broken_plugin": "ImportError"}` | `PluginLoader.load_errors` | Identify broken plugin installs |
| Number of enabled plugins | `3` | Count of enabled plugins | Complexity of typical setups |
| Plugin refresh intervals | `{"weather": 300, "stocks": 300}` | Plugin config `refresh_seconds` | Understand polling load |

> **Note on error messages:** Plugin error messages are collected only for maintainer use (to identify common failures and fix them). These are **not** displayed on the public transparency site. Error messages are sanitized to strip any URLs, paths, or API key fragments before collection.

#### Automatic Coverage for Future Plugins

Plugin analytics uses **auto-discovery** — it iterates the `PluginRegistry` at collection time rather than maintaining a hardcoded list of plugin names. This means **any plugin added to the `plugins/` directory in the future is automatically covered by analytics with zero code changes**.

How it works:

1. FiestaBoard's plugin loader scans the `plugins/` directory for subdirectories containing a `manifest.json`
2. Each plugin is loaded into the `PluginRegistry` with its manifest metadata (id, name, version, category, settings schema)
3. The analytics collector iterates `registry.list_plugins()` to enumerate **all** plugins — current and future
4. For each plugin, the collector reads: enabled/disabled state, plugin state (active/error/setup), and sanitized error messages
5. Plugin metadata from the manifest (id, version, category) is included — but **never** plugin configuration values

```python
# Pseudocode: how analytics auto-discovers plugins
def collect_plugin_analytics():
    registry = get_plugin_registry()
    plugin_data = {}

    for plugin_id, plugin in registry.plugins.items():
        manifest = registry.get_manifest(plugin_id)
        result = registry.fetch_plugin_data(plugin_id)

        plugin_data[plugin_id] = {
            "state": determine_state(result),  # "active", "error", or "setup"
            "version": manifest.get("version"),
            "category": manifest.get("category"),
            "error": sanitize(result.error) if result.error else None,
        }

    return plugin_data
```

**What this means for plugin developers:** When you create a new plugin using the `_template/` scaffold and place it in `plugins/`, analytics will automatically track its adoption, state, and any errors — with no extra configuration needed. The `manifest.json` already declares everything analytics needs (id, name, version, category).

#### Page & Content Analytics

| Data Point | Example Value | Source | Purpose |
|---|---|---|---|
| Total page count | `5` | `PageService.list_pages()` | Content complexity |
| Pages by type | `{"single": 2, "composite": 2, "template": 1}` | `Page.page_type` | Which page types are popular |
| Template names used | `["weather_basic", "stocks_ticker"]` | `Page.template` metadata | Which templates are popular |
| Average page duration (seconds) | `300` | `Page.duration_seconds` | How long content is displayed |

#### Board Content Characteristics (Anonymous — Never Message Content)

These metrics describe *what kind* of content is shown without revealing *what* the content says. Derived from the 6×22 character code grid (codes 0–71) after rendering.

| Data Point | Example Value | Source | Purpose |
|---|---|---|---|
| Blank space count (avg per board) | `42` | Count of code `0` in 6×22 grid | How much of the board is used vs empty |
| Letter count (avg per board) | `55` | Count of codes `1-26` in grid | Text density |
| Number count (avg per board) | `12` | Count of codes `27-36` in grid | Numeric content prevalence |
| Symbol count (avg per board) | `8` | Count of codes `37-62` in grid | Punctuation/symbol usage |
| Color tile count (avg per board) | `15` | Count of codes `63-71` in grid | How much color is used |
| Color tile breakdown | `{"red": 3, "green": 5, "blue": 7}` | Count per color code `63-70` | Which colors are popular |
| Board fill percentage (avg) | `68%` | `(132 - blank_count) / 132 * 100` | How full boards typically are |

> **Critical privacy note:** We count character *categories* (letters, numbers, symbols, colors, blanks) — we NEVER capture the actual character codes, sequences, or positions. `55 letters` tells us the board has text; it does NOT tell us what the text says.

#### Schedule Analytics

| Data Point | Example Value | Source | Purpose |
|---|---|---|---|
| Schedule mode enabled | `true` | Settings service | Is scheduling being used |
| Number of schedule entries | `6` | `ScheduleService.list_schedules()` | Schedule complexity |
| Day patterns used | `{"all": 2, "weekdays": 3, "custom": 1}` | `ScheduleEntry.day_pattern` | How people structure their schedules |
| Has default page set | `true` | Settings service | Gap-fill behavior |
| Silence schedule enabled | `true` | `config.json → features.silence_schedule.enabled` | Nighttime silence adoption |

#### Message Update Frequency

| Data Point | Example Value | Source | Purpose |
|---|---|---|---|
| Board updates sent (last 24h) | `48` | Counter in `DisplayService` | How often the board changes |
| Board updates skipped — unchanged (last 24h) | `240` | Counter in `DisplayService` | Cache hit rate |
| Board updates skipped — silence mode (last 24h) | `96` | Counter in `DisplayService` | Silence mode effectiveness |
| Board send failures (last 24h) | `2` | Counter in `DisplayService` | Board connectivity issues |
| Average time between board changes (minutes) | `30` | Derived from update counter | Content rotation speed |

#### Transition Animation Analytics

| Data Point | Example Value | Source | Purpose |
|---|---|---|---|
| Transition strategy | `"column"` or `null` | `config.json → board.transition_strategy` | Which animations are popular |
| Custom transition interval set | `true`/`false` | Whether `transition_interval_ms` is non-null | Are users customizing animations |
| Custom transition step size set | `true`/`false` | Whether `transition_step_size` is non-null | Are users customizing animations |
| Per-page transition overrides count | `2` | Pages with non-null transition settings | Page-level animation usage |

### Level 3: Diagnostics (Maintainer-Only — NOT on Public Site)

Error details for debugging. Transmitted to the ingest service but **never** shown on the public transparency site.

| Data Point | Example Value | Source | Purpose |
|---|---|---|---|
| Plugin error details (sanitized) | `{"stocks": "HTTPError 429"}` | `PluginResult.error` | Debug plugin API issues |
| Plugin load failures | `{"bad_plugin": "ModuleNotFoundError: No module named 'foo'"}` | `PluginLoader.load_errors` | Identify dependency issues |
| Board API connection errors (last 24h) | `3` | Counter in `BoardClient` | Track board connectivity |
| Board API error types | `["ConnectionTimeout", "HTTPError 401"]` | `BoardClient` error handling | Diagnose board API issues |
| Config validation errors | `["Missing board.host"]` | `ConfigManager.validate()` | Identify setup problems |
| Last error timestamp (relative) | `"2h ago"` | Relative time, not absolute | Recency of issues |

> **Sanitization rules for error messages:**
> - Strip file paths (replace with `<path>`)
> - Strip URLs (replace with `<url>`)
> - Strip anything resembling an API key (replace with `<key>`)
> - Strip IP addresses (replace with `<ip>`)
> - Keep only the error type and generic message

### What Is NEVER Collected

| Category | Examples | Why Not |
|---|---|---|
| **Message content** | Actual text on the board, character sequences, word patterns | Core privacy principle — we never read your messages |
| **Character positions or sequences** | Which characters are in which cells | Could reconstruct messages |
| **API keys or credentials** | Weather API key, board API key, HA access token | Sensitive secrets |
| **Location data** | Cities, ZIP codes, coordinates, lat/lng | Personally identifying |
| **Network information** | IP addresses, MAC addresses, hostnames, WiFi SSIDs | Personally identifying |
| **Home Assistant data** | Entity names, states, URLs, device names | Third-party private data |
| **Personal configuration** | Stock symbols, surf spots, transit stops, WiFi passwords | Reveals personal interests/location |
| **Timestamps** | Absolute times, timezone names | Could correlate with geography |
| **File paths** | Config file locations, plugin install paths | Reveals system info |

---

## Workstream 1: FiestaBoard App Implementation

### Config Changes

Add an `analytics` section to `config.json`:

```json
{
  "analytics": {
    "enabled": false,
    "level": "basic",
    "installation_id": null,
    "diagnostics_enabled": false,
    "last_sent": null
  }
}
```

- `enabled`: Always `false` by default (opt-out)
- `level`: `"basic"` or `"usage"` — controls how much data is shared
- `installation_id`: Auto-generated UUID v4 on first opt-in, stored locally
- `diagnostics_enabled`: Separate opt-in for error/diagnostics data (Level 3)
- `last_sent`: ISO timestamp of last successful send (for once-per-day scheduling)

### New Backend Module: `src/analytics/`

| File | Responsibility |
|---|---|
| `__init__.py` | Module init |
| `collector.py` | Gathers all metrics from config, plugins, pages, schedules, counters |
| `counters.py` | In-memory counters for board updates, errors, send stats (reset daily) |
| `content_stats.py` | Analyzes 6×22 board grid to produce anonymous content characteristics (character category counts, color breakdown, fill %) — never captures actual content |
| `sanitizer.py` | Strips sensitive data from error messages (paths, URLs, IPs, keys) |
| `sender.py` | Builds JSON payload, logs it, sends via HTTPS POST |
| `payload.py` | Defines the exact JSON schema for each level (Basic, Usage, Diagnostics) |

### Payload Schema

```json
{
  "schema_version": 1,
  "level": "usage",
  "timestamp_utc": "2026-02-20T07:00:00Z",

  "basic": {
    "installation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "version": "1.32.44",
    "platform": "linux/arm64",
    "python_version": "3.11.2",
    "board_api_mode": "local",
    "output_target": "board",
    "uptime_hours": 168
  },

  "usage": {
    "plugins": {
      "enabled": ["weather", "stocks", "muni", "date_time"],
      "states": {
        "weather": "active",
        "stocks": "error",
        "muni": "active",
        "date_time": "active"
      },
      "count": 4
    },
    "pages": {
      "total": 5,
      "by_type": { "single": 2, "composite": 2, "template": 1 },
      "templates_used": ["weather_basic", "stocks_ticker"],
      "avg_duration_seconds": 300
    },
    "content": {
      "avg_blank_spaces": 42,
      "avg_letter_count": 55,
      "avg_number_count": 12,
      "avg_symbol_count": 8,
      "avg_color_tile_count": 15,
      "color_breakdown": { "red": 3, "orange": 0, "yellow": 2, "green": 5, "blue": 7, "violet": 0, "white": 3, "black": 0 },
      "avg_fill_percentage": 68
    },
    "schedules": {
      "schedule_mode_enabled": true,
      "entry_count": 6,
      "day_patterns": { "all": 2, "weekdays": 3, "custom": 1 },
      "has_default_page": true,
      "silence_schedule_enabled": true
    },
    "updates": {
      "board_sends_24h": 48,
      "board_skipped_unchanged_24h": 240,
      "board_skipped_silence_24h": 96,
      "board_send_failures_24h": 2,
      "avg_minutes_between_changes": 30
    },
    "transitions": {
      "strategy": "column",
      "custom_interval": false,
      "custom_step_size": false,
      "per_page_overrides": 2
    }
  },

  "diagnostics": {
    "plugin_errors": { "stocks": "HTTPError 429" },
    "plugin_load_errors": {},
    "board_api_errors_24h": 3,
    "board_api_error_types": ["ConnectionTimeout"],
    "config_validation_errors": [],
    "last_error_relative": "2h ago"
  }
}
```

### Frontend Settings UI

Add an "Analytics" card to the existing Settings page:

```
┌──────────────────────────────────────────────────┐
│  📊 Analytics                                    │
│                                                  │
│  Help improve FiestaBoard by sharing anonymous   │
│  usage data. No message content is ever sent.    │
│                                                  │
│  [  OFF  /  ON  ]     ← Toggle (default: OFF)   │
│                                                  │
│  Level:  ○ Basic   ● Usage                       │
│                                                  │
│  □ Include diagnostics (error details            │
│    for maintainers — not shown publicly)         │
│                                                  │
│  [▸ What do we collect?]   ← Expandable details  │
│  [▸ Preview payload]       ← Shows exact JSON    │
│                                                  │
│  Status: Last sent 2h ago ✓                      │
└──────────────────────────────────────────────────┘
```

### In-Memory Counters

New counters tracked in the `DisplayService` main loop (reset every 24 hours):

```python
class AnalyticsCounters:
    board_sends: int = 0              # Successful send_characters() calls
    board_skipped_unchanged: int = 0  # Skipped because content unchanged
    board_skipped_silence: int = 0    # Skipped because silence mode active
    board_send_failures: int = 0      # Failed send_characters() calls
    board_api_error_types: List[str]  # Deduplicated error type names
    last_error_time: Optional[datetime]
    content_stats_samples: List[dict] # Rolling window of last N content snapshots
```

Content stats are sampled from the 6×22 grid whenever a board update is sent. The last N samples (e.g., 10) are averaged to produce the daily `content` section.

---

## Workstream 2: Cloud Ingest Service (New Repo)

### Repository: `Fiestaboard/analytics-ingest`

A lightweight AWS serverless stack to receive, store, and aggregate telemetry payloads.

### Architecture (AWS Serverless — Minimal Cost)

```
                                ┌─────────────────────────┐
  HTTPS POST /v1/telemetry ───> │  API Gateway (HTTP API) │  ← Free tier: 1M requests/mo
                                └───────────┬─────────────┘
                                            │
                                ┌───────────▼─────────────┐
                                │  Lambda: ingest         │  ← Free tier: 1M invocations/mo
                                │  - Validate schema      │
                                │  - Check rate limit     │
                                │  - Strip any PII        │
                                │  - Write to DynamoDB    │
                                └───────────┬─────────────┘
                                            │
                                ┌───────────▼─────────────┐
                                │  DynamoDB               │  ← Free tier: 25 GB, 25 WCU
                                │  Table: telemetry       │
                                │  PK: installation_id    │
                                │  SK: timestamp          │
                                │  TTL: 90 days           │
                                └───────────┬─────────────┘
                                            │
                                ┌───────────▼─────────────┐
                                │  Lambda: aggregate      │  ← Cron: daily via EventBridge
                                │  - Scan last 24h data   │
                                │  - Compute aggregates   │
                                │  - Write JSON to S3     │
                                └───────────┬─────────────┘
                                            │
                                ┌───────────▼─────────────┐
                                │  S3: aggregated-data    │  ← Public JSON files
                                │  - summary.json         │
                                │  - plugins.json         │
                                │  - versions.json        │
                                └─────────────────────────┘
```

### Why AWS Serverless?

| Requirement | Solution |
|---|---|
| As cheap as possible | Pay-per-use pricing; most services have always-free tiers |
| No earned revenue | Designed to stay under $5/month even at scale |
| Low maintenance | Serverless = no servers to patch, no OS updates, no uptime monitoring |
| Scalable if FiestaBoard grows | Lambda + DynamoDB scale automatically from 10 to 100,000 installations |
| Secure | API Gateway enforces TLS; Lambda runs in isolated containers |

### Real AWS Cost Breakdown

Below are actual AWS prices (as of early 2026) with worked math for three realistic scenarios. All prices are for **us-east-1** region. Prices may vary slightly by region.

#### AWS Per-Unit Pricing Reference

| Service | Unit | Price | Free Tier | Free Tier Expiry |
|---|---|---|---|---|
| **API Gateway** (HTTP API) | 1M requests | $1.00 | 1M requests/mo | 12 months |
| **Lambda** (requests) | 1M invocations | $0.20 | 1M invocations/mo | **Never** (always free) |
| **Lambda** (compute) | 1 GB-second | $0.0000167 | 400,000 GB-sec/mo | **Never** (always free) |
| **DynamoDB** (on-demand writes) | 1M write request units | $1.25 | 25 WCU provisioned | **Never** (always free) |
| **DynamoDB** (on-demand reads) | 1M read request units | $0.25 | 25 RCU provisioned | **Never** (always free) |
| **DynamoDB** (storage) | 1 GB/month | $0.25 | 25 GB | **Never** (always free) |
| **S3** (storage) | 1 GB/month | $0.023 | 5 GB | 12 months |
| **S3** (PUT requests) | 1,000 requests | $0.005 | 2,000 PUTs/mo | 12 months |
| **S3** (GET requests) | 1,000 requests | $0.0004 | 20,000 GETs/mo | 12 months |
| **CloudFront** | 1 TB transfer out | ~$0.085 | 1 TB/mo + 10M requests | **Never** (always free) |
| **EventBridge** (scheduled rules) | 1 invocation | $0.0000546 | — | — |
| **Route 53** (hosted zone) | 1 zone/month | $0.50 | — | — |
| **Route 53** (DNS queries) | 1M queries | $0.40 | — | — |

#### Scenario 1: Early Stage — 100 Installations

100 FiestaBoard installations opt in, each sending 1 payload (~2KB) per day.

| Service | Monthly Usage | Calculation | Monthly Cost |
|---|---|---|---|
| API Gateway | 3,000 requests | 100 installs × 30 days | **$0.00** (within free tier) |
| Lambda: ingest | 3,000 invocations, ~1.5 GB-sec | 128MB × 0.5s per invocation | **$0.00** (always-free tier) |
| Lambda: aggregate | 30 invocations, ~15 GB-sec | 512MB × 1s daily | **$0.00** (always-free tier) |
| DynamoDB writes | 3,000 writes/mo | 1 write per payload | **$0.00** (on-demand: $0.004) |
| DynamoDB reads | ~3,100 reads/mo | Daily scan for aggregation | **$0.00** (on-demand: $0.001) |
| DynamoDB storage | ~18 MB | 100 installs × 2KB × 90 days | **$0.00** (under 25 GB always-free) |
| S3 storage | <1 MB | 3 JSON files, updated daily | **$0.00** (under 5 GB free tier) |
| S3 requests | ~60 PUTs, ~5,000 GETs | Daily writes + public site reads | **$0.00** (within free tier) |
| CloudFront | <100 MB transfer | Public site traffic | **$0.00** (within always-free tier) |
| EventBridge | 30 invocations | 1 daily cron | **$0.00** ($0.002) |
| Route 53 zone | 1 hosted zone | analytics.fiestaboard.com | **$0.50** |
| Route 53 queries | ~5,000 queries | DNS lookups | **$0.00** ($0.002) |
| | | | |
| **Total (Year 1)** | | API Gateway in free trial | **$0.50/mo ($6.00/yr)** |
| **Total (Year 2+)** | | API Gateway free tier expired | **$0.50/mo ($6.00/yr)** |

> At 100 installations, all usage is so small that per-request costs round to $0.00 even after the 12-month free tier expires. The only fixed cost is the Route 53 hosted zone.

#### Scenario 2: Growth Stage — 1,000 Installations

1,000 installations opt in, each sending 1 payload per day.

| Service | Monthly Usage | Calculation | Monthly Cost |
|---|---|---|---|
| API Gateway | 30,000 requests | 1,000 × 30 days | **$0.00** (free tier Year 1) |
| Lambda: ingest | 30,000 invocations, ~15 GB-sec | | **$0.00** (always-free tier) |
| Lambda: aggregate | 30 invocations, ~30 GB-sec | Larger scan | **$0.00** (always-free tier) |
| DynamoDB writes | 30,000 writes/mo | | **$0.04** (on-demand) |
| DynamoDB reads | ~31,000 reads/mo | | **$0.01** (on-demand) |
| DynamoDB storage | ~180 MB | 1,000 × 2KB × 90 days | **$0.00** (under 25 GB) |
| S3 | <1 MB storage, ~60 PUTs, ~50,000 GETs | Public site traffic up | **$0.02** |
| CloudFront | <500 MB transfer | | **$0.00** (always-free tier) |
| EventBridge | 30 invocations | | **$0.00** |
| Route 53 | 1 zone + ~50,000 queries | | **$0.52** |
| | | | |
| **Total (Year 1)** | | API Gateway in free trial | **$0.59/mo ($7.08/yr)** |
| **Total (Year 2+)** | | API Gateway: 30K req × $1/1M = $0.03 | **$0.62/mo ($7.44/yr)** |

#### Scenario 3: Mature Stage — 5,000 Installations

5,000 installations opt in, each sending 1 payload per day.

| Service | Monthly Usage | Calculation | Monthly Cost |
|---|---|---|---|
| API Gateway | 150,000 requests | 5,000 × 30 days | **$0.00** (free tier Year 1) |
| Lambda: ingest | 150,000 invocations, ~75 GB-sec | | **$0.00** (always-free tier) |
| Lambda: aggregate | 30 invocations, ~150 GB-sec | Larger scans | **$0.00** (always-free tier) |
| DynamoDB writes | 150,000 writes/mo | | **$0.19** (on-demand) |
| DynamoDB reads | ~155,000 reads/mo | | **$0.04** (on-demand) |
| DynamoDB storage | ~900 MB | 5,000 × 2KB × 90 days | **$0.00** (under 25 GB) |
| S3 | <1 MB, ~60 PUTs, ~200,000 GETs | | **$0.08** |
| CloudFront | <2 GB transfer | | **$0.00** (always-free tier) |
| EventBridge | 30 invocations | | **$0.00** |
| Route 53 | 1 zone + ~200,000 queries | | **$0.58** |
| | | | |
| **Total (Year 1)** | | API Gateway in free trial | **$0.89/mo ($10.68/yr)** |
| **Total (Year 2+)** | | API Gateway: 150K req × $1/1M = $0.15 | **$1.04/mo ($12.48/yr)** |

#### Cost Summary Table

| Scenario | Installations | Year 1 Monthly | Year 2+ Monthly | Annual Cost (Year 2+) |
|---|---|---|---|---|
| **Early** | 100 | $0.50 | $0.50 | **$6.00/yr** |
| **Growth** | 1,000 | $0.59 | $0.62 | **$7.44/yr** |
| **Mature** | 5,000 | $0.89 | $1.04 | **$12.48/yr** |
| **Large** (extrapolated) | 10,000 | $1.48 | $1.78 | **$21.36/yr** |

> **Bottom line:** The entire analytics infrastructure costs between **$6 and $22 per year** depending on scale. The dominant cost is the $0.50/month Route 53 hosted zone — everything else is pennies. Even at 10,000 installations, the total annual cost is about the price of two months of Netflix.

#### Optional: Skip Route 53 Entirely

If we use a subdomain on an existing domain (e.g., GitHub Pages CNAME, or Cloudflare DNS pointing to the API Gateway URL), the Route 53 cost disappears entirely:

| Scenario | Without Route 53 | Annual Cost |
|---|---|---|
| 100 installations | $0.00/mo | **~$0/yr** |
| 1,000 installations | $0.12/mo | **$1.44/yr** |
| 5,000 installations | $0.54/mo | **$6.48/yr** |

#### What Could Cause Unexpected Costs?

| Risk | Impact | Mitigation |
|---|---|---|
| DDoS on the ingest endpoint | Millions of Lambda invocations + DynamoDB writes | API Gateway throttle (100 req/sec default), Lambda concurrency limit (10), DynamoDB on-demand auto-scaling with billing alarm |
| Runaway installations sending too frequently | Higher-than-expected request volume | Rate limiting in Lambda (1 per install per 20h), payload size cap (10KB) |
| DynamoDB storage growth | Storage costs if TTL stops working | TTL is built into DynamoDB — it auto-deletes. Set CloudWatch alarm on table size >1 GB |
| Forgetting to set up billing alerts | Surprise bill | **Step 1 of deployment: set $5/month billing alarm in AWS Budgets (free)** |

**Recommended safeguard:** Set a **$5/month AWS Budget alarm** as the very first step of deployment. This sends an email alert if projected costs exceed $5 — giving time to investigate before any real cost accumulates.

### Ingest Lambda: Key Logic

```python
# Pseudocode for ingest Lambda
def handler(event, context):
    payload = json.loads(event['body'])

    # 1. Validate schema version
    if payload.get('schema_version') != 1:
        return {'statusCode': 400, 'body': 'Unknown schema'}

    # 2. Validate installation_id format (UUID v4)
    if not is_valid_uuid(payload['basic']['installation_id']):
        return {'statusCode': 400, 'body': 'Invalid ID'}

    # 3. Rate limit: max 1 payload per installation per 20 hours
    if was_recently_sent(payload['basic']['installation_id']):
        return {'statusCode': 429, 'body': 'Too frequent'}

    # 4. Defense-in-depth: strip any unexpected fields
    clean = strip_to_schema(payload)

    # 5. Write to DynamoDB with 90-day TTL
    dynamodb.put_item(
        TableName='telemetry',
        Item={
            'installation_id': clean['basic']['installation_id'],
            'timestamp': clean['timestamp_utc'],
            'data': clean,
            'ttl': int(time.time()) + (90 * 86400)
        }
    )

    return {'statusCode': 200, 'body': 'OK'}
```

### Aggregation Lambda: Daily Cron

Runs daily via EventBridge rule. Scans all records from the last 24 hours and produces aggregated JSON files:

**`summary.json`** — Written to S3, served publicly:
```json
{
  "generated_at": "2026-02-20T00:00:00Z",
  "total_installations": 342,
  "active_last_30d": 285,
  "version_distribution": {
    "1.32.44": 180,
    "1.32.43": 95,
    "1.31.0": 10
  },
  "platform_distribution": {
    "linux/arm64": 220,
    "linux/amd64": 100,
    "darwin/arm64": 22
  },
  "board_api_mode": {
    "local": 290,
    "cloud": 52
  }
}
```

**`plugins.json`** — Plugin popularity:
```json
{
  "generated_at": "2026-02-20T00:00:00Z",
  "plugin_usage": {
    "weather": { "enabled_count": 280, "active": 270, "error": 8, "setup": 2 },
    "date_time": { "enabled_count": 310, "active": 308, "error": 1, "setup": 1 },
    "stocks": { "enabled_count": 95, "active": 88, "error": 5, "setup": 2 },
    "muni": { "enabled_count": 45, "active": 42, "error": 2, "setup": 1 }
  },
  "avg_plugins_per_install": 3.2
}
```

**`content.json`** — Anonymous content characteristics:
```json
{
  "generated_at": "2026-02-20T00:00:00Z",
  "avg_board_fill_percentage": 65,
  "avg_color_tiles_per_board": 12,
  "most_popular_colors": ["green", "red", "blue"],
  "avg_updates_per_day": 45,
  "avg_pages_per_install": 4.2,
  "page_type_distribution": { "single": 45, "composite": 35, "template": 20 }
}
```

### Infrastructure as Code: Deployment Technology

We need a tool to define our entire AWS stack (API Gateway, Lambda, DynamoDB, S3, EventBridge, CloudFront) as code so it can be deployed repeatably, version-controlled, and updated safely. Here's a comparison of the major options:

#### Options Evaluated

| Tool | What It Is | Language | License |
|---|---|---|---|
| **AWS SAM** | AWS-native serverless deployment framework built on CloudFormation | YAML templates | Apache 2.0 (open source) |
| **Terraform** | Multi-cloud Infrastructure as Code tool by HashiCorp | HCL (HashiCorp Config Language) | BSL 1.1 (source-available, **not** open source since Aug 2023) |
| **OpenTofu** | Community fork of Terraform, maintained by Linux Foundation | HCL | Apache 2.0 (open source) |
| **AWS CDK** | AWS Infrastructure as Code using programming languages | TypeScript, Python, etc. | Apache 2.0 (open source) |
| **SST** | Modern serverless framework built on AWS CDK | TypeScript | MIT (open source) |

#### Detailed Comparison

| Factor | AWS SAM | Terraform / OpenTofu | AWS CDK | SST |
|---|---|---|---|---|
| **Learning curve** | Low — simplified YAML, great docs | Medium — HCL syntax, state management | Medium — mixing code + CloudFormation concepts | Medium — TypeScript + CDK concepts |
| **Local testing** | ✅ Built-in (`sam local invoke`, `sam local start-api`) | ❌ No built-in Lambda emulation | ❌ No built-in (use SAM CLI alongside) | ✅ Live Lambda dev mode |
| **Multi-cloud** | ❌ AWS only | ✅ AWS, Azure, GCP, 100+ providers | ❌ AWS only | ❌ AWS only |
| **Serverless focus** | ✅ Purpose-built for Lambda + API GW + DynamoDB | ⚠️ Generic — serverless is one of many use cases | ⚠️ Generic — supports everything | ✅ Serverless-focused |
| **Deploy command** | `sam build && sam deploy` | `terraform apply` / `tofu apply` | `cdk deploy` | `sst deploy` |
| **Rollback** | ✅ Automatic (CloudFormation) | ⚠️ Manual state management | ✅ Automatic (CloudFormation) | ✅ Automatic (CloudFormation) |
| **State management** | None needed (CloudFormation manages it) | Requires S3 bucket + DynamoDB lock table for remote state | None needed (CloudFormation manages it) | None needed (CloudFormation manages it) |
| **CI/CD integration** | ✅ `sam deploy` in GitHub Actions | ✅ `terraform apply` in GitHub Actions | ✅ `cdk deploy` in GitHub Actions | ✅ `sst deploy` in GitHub Actions |
| **Template verbosity for our stack** | ~60 lines YAML for all resources | ~150 lines HCL for same resources | ~80 lines TypeScript | ~50 lines TypeScript |
| **Community size** | Large (AWS-backed) | Very large (but split: Terraform vs OpenTofu) | Growing (AWS-backed) | Smaller, startup-focused |
| **License concerns** | None (Apache 2.0) | ⚠️ Terraform: BSL 1.1 — not open source. OpenTofu: Apache 2.0 | None (Apache 2.0) | None (MIT) |

#### Recommendation: **AWS SAM**

For the FiestaBoard analytics ingest service, **AWS SAM** is the best fit. Here's why:

1. **Purpose-built for exactly our stack.** SAM was designed for Lambda + API Gateway + DynamoDB + S3 + EventBridge. Our entire infrastructure is ~60 lines of YAML — no boilerplate, no abstractions to learn.

2. **Lowest learning curve.** A contributor who has never used IaC before can read a SAM template and understand it. YAML is declarative and self-documenting. Compare that to learning HCL (Terraform) or mixing TypeScript with CDK constructs.

3. **No state management headache.** SAM uses CloudFormation under the hood, which manages state automatically in AWS. Terraform/OpenTofu require setting up a separate S3 bucket + DynamoDB table just to store infrastructure state — that's more infrastructure to manage our infrastructure.

4. **Built-in local testing.** `sam local invoke` and `sam local start-api` let contributors test Lambda functions on their laptop without deploying to AWS. This is critical for an open source project where contributors may not have AWS accounts.

5. **Simple deployment.** Two commands: `sam build && sam deploy --guided`. The guided deploy walks you through every setting. After the first deploy, `sam deploy` is a single command.

6. **Open source license.** SAM is Apache 2.0 — no licensing concerns for an open source project. Terraform's BSL 1.1 license is source-available but **not** open source, which is a philosophical mismatch for FiestaBoard.

7. **Zero extra cost.** SAM is a CLI tool + template format. It compiles down to CloudFormation, which is free. No additional services or subscriptions.

#### Why Not Terraform?

Terraform is the most popular IaC tool and many people's first instinct, but it has drawbacks for this specific use case:

- **License concern:** In August 2023, HashiCorp changed Terraform's license from MPL 2.0 (open source) to BSL 1.1 (source-available, not open source). This restricts competitors from offering Terraform-as-a-service. While this doesn't directly affect FiestaBoard (we're not a competitor to HashiCorp), using a non-open-source tool to deploy an open source project's infrastructure is a philosophical mismatch. The community fork **OpenTofu** (Apache 2.0, Linux Foundation) is the open source alternative, but it's still maturing.

- **State management overhead:** Terraform requires a "backend" to store infrastructure state. For AWS, this means creating an S3 bucket + DynamoDB lock table before you can even begin deploying the actual infrastructure. SAM/CloudFormation manages state automatically — zero setup.

- **Not serverless-focused:** Terraform is a general-purpose IaC tool. Defining a Lambda + API Gateway setup requires ~150 lines of HCL with explicit IAM roles, policies, and resource connections. SAM does this in ~60 lines with built-in shortcuts like `Events: Api:` that auto-create API Gateway routes.

- **Overkill for our scope:** We're deploying 6 AWS resources. Terraform's power shines for complex multi-cloud, multi-environment setups with dozens of services. For a simple serverless stack, it adds unnecessary complexity.

#### Why Not CDK or SST?

- **CDK** requires contributors to know TypeScript or Python AND understand CloudFormation constructs. It's powerful but adds a layer of abstraction that's unnecessary for a simple stack.
- **SST** is excellent for TypeScript-heavy serverless projects but is a younger ecosystem with more frequent breaking changes. It also requires a TypeScript toolchain — our analytics ingest is Python Lambda functions, so TypeScript would only be used for infrastructure, not application code.

#### What Deployment Looks Like

With SAM, deploying the entire analytics stack is this simple:

```bash
# First time setup (one-time, interactive)
$ pip install aws-sam-cli
$ cd analytics-ingest
$ sam build
$ sam deploy --guided

# Subsequent deployments (one command)
$ sam build && sam deploy
```

The `sam deploy --guided` flow:
```
Setting default arguments for 'sam deploy'
=========================================
Stack Name [fiestaboard-analytics]:
AWS Region [us-east-1]:
Confirm changes before deploy [Y/n]: y
Allow SAM CLI IAM role creation [Y/n]: y
Save arguments to configuration file [Y/n]: y

Deploying...
✓ API Gateway created
✓ Ingest Lambda deployed
✓ Aggregate Lambda deployed
✓ DynamoDB table created
✓ S3 bucket created
✓ EventBridge rule created
✓ CloudFront distribution created

Outputs:
  ApiUrl: https://abc123.execute-api.us-east-1.amazonaws.com/v1/telemetry
```

#### Example SAM Template (Our Actual Stack)

This is approximately what the full `template.yaml` would look like:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: FiestaBoard Analytics Ingest Service

Globals:
  Function:
    Timeout: 10
    Runtime: python3.12
    MemorySize: 128

Resources:
  # DynamoDB table for telemetry storage
  TelemetryTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: fiestaboard-telemetry
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: installation_id
          AttributeType: S
        - AttributeName: timestamp
          AttributeType: S
      KeySchema:
        - AttributeName: installation_id
          KeyType: HASH
        - AttributeName: timestamp
          KeyType: RANGE
      TimeToLiveSpecification:
        AttributeName: ttl
        Enabled: true

  # S3 bucket for aggregated public JSON
  AggregatedDataBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: fiestaboard-analytics-public

  # Ingest Lambda — receives daily telemetry payloads
  IngestFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/ingest/
      Handler: handler.lambda_handler
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref TelemetryTable
      Events:
        TelemetryApi:
          Type: HttpApi
          Properties:
            Path: /v1/telemetry
            Method: POST

  # Aggregation Lambda — daily cron to compute stats
  AggregateFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/aggregate/
      Handler: handler.lambda_handler
      MemorySize: 512
      Timeout: 60
      Policies:
        - DynamoDBReadPolicy:
            TableName: !Ref TelemetryTable
        - S3CrudPolicy:
            BucketName: !Ref AggregatedDataBucket
      Events:
        DailyCron:
          Type: Schedule
          Properties:
            Schedule: cron(0 2 * * ? *)
            Description: Daily aggregation at 2 AM UTC

Outputs:
  ApiUrl:
    Description: Telemetry ingest endpoint
    Value: !Sub "https://${ServerlessHttpApi}.execute-api.${AWS::Region}.amazonaws.com/v1/telemetry"
  BucketName:
    Description: S3 bucket for aggregated data
    Value: !Ref AggregatedDataBucket
```

**That's the entire infrastructure** — API Gateway, 2 Lambda functions, DynamoDB with TTL, S3, and a daily EventBridge cron — in ~70 lines of readable YAML.

#### CI/CD: GitHub Actions Deployment

Deployments can be automated via GitHub Actions in the `analytics-ingest` repo:

```yaml
# .github/workflows/deploy.yml
name: Deploy Analytics Stack
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - uses: aws-actions/setup-sam@v2
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - run: sam build
      - run: sam deploy --no-confirm-changeset --no-fail-on-empty-changeset
```

Merging to `main` automatically deploys the stack. No manual steps, no SSH into servers, no downtime.

#### Repository Structure (Updated)

```
analytics-ingest/
├── template.yaml          # SAM template — defines ALL infrastructure
├── samconfig.toml         # Deployment defaults (region, stack name)
├── src/
│   ├── ingest/            # Ingest Lambda function
│   │   ├── handler.py
│   │   ├── validator.py
│   │   └── requirements.txt
│   └── aggregate/         # Aggregation Lambda function
│       ├── handler.py
│       ├── aggregator.py
│       └── requirements.txt
├── tests/
│   ├── test_ingest.py
│   └── test_aggregate.py
├── .github/
│   └── workflows/
│       └── deploy.yml     # Auto-deploy on merge to main
└── README.md
```

---

## Workstream 3: Public Transparency Site (New Repo)

### Repository: `Fiestaboard/analytics-public`

A simple static site that displays aggregated analytics data. Similar to [analytics.home-assistant.io](https://analytics.home-assistant.io/).

### Purpose

- **Transparency**: Users can see exactly what aggregate data looks like
- **Trust**: Shows we only have anonymous, aggregated numbers
- **Community**: Fun to see FiestaBoard's growth and popular plugins

### Architecture

```
analytics-public/
├── src/
│   ├── index.html         # Main page
│   ├── styles.css         # Simple styling
│   └── app.js             # Fetch JSON from S3, render charts
├── public/                # Static assets
└── README.md
```

- **Hosting**: S3 + CloudFront (free tier) or GitHub Pages (free)
- **Domain**: `analytics.fiestaboard.com` (optional)
- **Data source**: Reads JSON files from the S3 bucket (Workstream 2 output)
- **Charts**: Lightweight JS library (e.g., Chart.js at ~60KB)
- **Updates**: Automatically refreshed when aggregation Lambda runs daily

### What the Public Site Shows

| Section | Content | Data Source |
|---|---|---|
| **Installations** | Total active installations, 30-day trend | `summary.json` |
| **Versions** | Pie chart of version distribution | `summary.json` |
| **Platforms** | Bar chart of linux/arm64 vs amd64 vs macOS | `summary.json` |
| **Plugins** | Ranked list of most popular plugins | `plugins.json` |
| **Plugin Health** | % of plugins in active vs error state | `plugins.json` |
| **Content** | Average board fill %, color usage, updates/day | `content.json` |
| **Pages** | Avg pages per install, type breakdown | `content.json` |

### What the Public Site NEVER Shows

- Individual installation data
- Error messages or diagnostic details
- Any data that could identify a specific user
- Raw telemetry payloads

---

## Security Considerations

### Data in Transit
- All telemetry is sent over **HTTPS only** (API Gateway enforces TLS 1.2+)
- No sensitive data is included in the payload (defense in depth)

### Data at Rest
- **User's device**: Only the installation UUID + opt-in flag stored in `config.json`
- **DynamoDB**: Anonymous data only, 90-day TTL auto-deletes old records
- **S3**: Only aggregated JSON files (no individual records)
- **Encryption**: DynamoDB + S3 encrypted at rest (AWS default)

### Network Safety (Local Network Concerns)
- Telemetry only sends **outbound** HTTPS requests — no inbound ports opened
- No listening services added to the user's network
- Payload is small (~2KB JSON) — negligible bandwidth
- Sent once per day — no continuous data stream
- If the network blocks outbound requests, the send silently fails (no retries, no error UI)

### API Security
- **Rate limiting**: API Gateway throttle + per-installation rate limit in Lambda (1 request per 20 hours)
- **Schema validation**: Only allowlisted fields accepted; unexpected fields stripped
- **No authentication needed**: Payloads contain no sensitive data, and the installation UUID is random
- **Abuse prevention**: Payload size limit (10KB max), DynamoDB write throttling

### Privacy Guarantees
- **No fingerprinting**: Installation UUID is randomly generated, not derived from hardware
- **No tracking across networks**: Moving the Pi to a new network doesn't change behavior
- **No correlation**: UUID cannot be linked to a person, household, or network
- **User control**: Opt-out at any time; stops all transmission immediately
- **Data deletion**: DynamoDB TTL auto-expires data; users can request immediate deletion
- **Open source**: All three repos (app, ingest, public site) are fully open source and auditable
- **Error sanitization**: All error messages stripped of paths, URLs, IPs, and API key fragments

### Threat Model

| Threat | Mitigation |
|---|---|
| Man-in-the-middle interception | HTTPS/TLS for all transmissions (API Gateway enforced) |
| Payload contains sensitive data | Allowlist-based validation in both app and Lambda |
| Server breach exposes user data | Only anonymous UUIDs + plugin names stored — no PII; DynamoDB encrypted at rest |
| Analytics enabled without consent | Default is `false`; requires explicit user action in UI |
| UUID used to track users | UUID is random, not hardware-derived; user can regenerate or delete |
| DDoS on ingest endpoint | API Gateway throttling + Lambda concurrency limits + rate limiting |
| Aggregated data reveals individuals | Minimum threshold: don't show stats for categories with <5 installations |

---

## User Experience Flow

```
1. User installs FiestaBoard
   └─> analytics.enabled = false (default)
       No data collected. No network requests.

2. User visits Settings page
   └─> Sees "Analytics" card (OFF by default)
       "Help improve FiestaBoard by sharing anonymous usage data"

3. User toggles ON
   └─> Shown explanation of what's collected
       Asked to choose level: Basic or Usage
       Optional checkbox: Include diagnostics
       "Preview what will be sent" button available

4. User confirms
   └─> installation_id generated (UUID v4)
       analytics.enabled = true written to config.json
       First payload sent after 15 minutes

5. Daily operation
   └─> Once per day, payload is built, logged at INFO, and sent via HTTPS
       If send fails, silently retried next day
       Counters reset after successful send

6. User toggles OFF
   └─> analytics.enabled = false
       No more data collected or sent
       Existing installation_id kept (in case user re-enables)
       Counters stop incrementing
```

---

## Alternatives Considered

### Grafana on the Pi
- **Rejected**: Too resource-heavy for a Raspberry Pi. Grafana + InfluxDB/Prometheus would add ~500MB RAM usage to a device already running FiestaBoard + board communication.

### PostHog Self-Hosted
- **Rejected**: Overkill. PostHog is designed for product analytics with session replay, feature flags, etc. Too heavy and expensive to run.

### Google Analytics / Mixpanel / Amplitude
- **Rejected**: Third-party services conflict with FiestaBoard's self-hosted ethos. Users won't trust sending data to big tech analytics platforms.

### VPS with SQLite + Grafana
- **Rejected**: Costs $5+/month for a VPS. Requires server maintenance, patching, monitoring. AWS serverless is cheaper and maintenance-free.

### Cloudflare Workers + KV
- **Considered**: Very cheap, but less flexible for aggregation queries. KV is key-value only — harder to scan and aggregate compared to DynamoDB.

### No Analytics (Status Quo)
- **Rejected**: Without usage data, development decisions are guesswork. Knowing which plugins are popular, what errors occur, and how boards are configured helps prioritize work.

---

## Implementation Phases

### Phase 1: FiestaBoard App — Backend Collection (Workstream 1)
- [ ] Add `analytics` config section with defaults
- [ ] Create `src/analytics/` module (collector, counters, content_stats, sanitizer, sender, payload)
- [ ] Add in-memory counters to `DisplayService` main loop
- [ ] Add content stats sampling on board updates
- [ ] Add daily send scheduler (once per 24h if opted in)
- [ ] Add transparency logging (log payload at INFO before send)
- [ ] Add unit tests for collector, sanitizer, and payload builder

### Phase 2: FiestaBoard App — Frontend Opt-In UI (Workstream 1)
- [ ] Add Analytics settings card to Settings page
- [ ] Toggle for enable/disable (default OFF)
- [ ] Level selector (Basic / Usage)
- [ ] Diagnostics opt-in checkbox
- [ ] "What do we collect?" expandable section
- [ ] "Preview payload" button
- [ ] Status indicator (last sent time)

### Phase 3: Cloud Ingest Service (Workstream 2)
- [ ] Create `Fiestaboard/analytics-ingest` repository
- [ ] AWS SAM template (`template.yaml`) for API Gateway + Lambda + DynamoDB + S3 + EventBridge
- [ ] Ingest Lambda with validation, rate limiting, schema enforcement
- [ ] Aggregation Lambda with daily cron
- [ ] Unit tests for both Lambdas
- [ ] CI/CD pipeline for deployment
- [ ] Domain setup (optional: `api.analytics.fiestaboard.com`)

### Phase 4: Public Transparency Site (Workstream 3)
- [ ] Create `Fiestaboard/analytics-public` repository
- [ ] Static site with Chart.js visualizations
- [ ] Fetch aggregated JSON from S3
- [ ] Sections: installations, versions, platforms, plugins, content stats
- [ ] Deploy via S3 + CloudFront or GitHub Pages
- [ ] Domain setup (optional: `analytics.fiestaboard.com`)

### Phase 5: Documentation & Launch
- [ ] User-facing docs explaining the analytics feature
- [ ] Blog post / changelog entry announcing the feature
- [ ] Link to public transparency site from Settings page
- [ ] Community feedback period before expanding collection
