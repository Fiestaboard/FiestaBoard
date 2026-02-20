# Analytics & Telemetry Plan

## Overview

This document proposes a privacy-first, opt-in analytics system for FiestaBoard. The goal is to understand how FiestaBoard is being used (which plugins are popular, common configurations, error rates) so that development efforts can be prioritized — while respecting users' privacy and the constraints of running on a local network.

**Key Principle:** Analytics must be **opt-in with a default of opt-out**. No data is ever collected or transmitted unless the user explicitly enables it.

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

## Recommended Approach for FiestaBoard

### Architecture: Lightweight Outbound Telemetry

Since FiestaBoard runs on users' local networks (often Raspberry Pi), we should **not** ask users to host an analytics server locally. Instead, the approach is:

1. **FiestaBoard backend** collects anonymous usage metrics locally
2. **On a schedule** (once per day), if the user has opted in, a small JSON payload is sent to a FiestaBoard project-owned endpoint
3. **The endpoint** ingests data into a lightweight analytics backend for the FiestaBoard maintainers

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│  User's Local Network       │         │  FiestaBoard Project Server  │
│                             │         │  (maintained by project)     │
│  ┌───────────────────────┐  │  HTTPS  │  ┌────────────────────────┐ │
│  │  FiestaBoard Backend  │──│────────>│──│  Ingest API Endpoint   │ │
│  │  (Python/FastAPI)     │  │ 1x/day  │  │  (simple POST handler) │ │
│  │                       │  │         │  └──────────┬─────────────┘ │
│  │  - Collects metrics   │  │         │             │               │
│  │  - Logs payload       │  │         │  ┌──────────▼─────────────┐ │
│  │  - Sends if opted in  │  │         │  │  Storage + Dashboard   │ │
│  └───────────────────────┘  │         │  │  (Umami, Grafana, or   │ │
│                             │         │  │   simple DB + charts)  │ │
└─────────────────────────────┘         │  └────────────────────────┘ │
                                        └──────────────────────────────┘
```

### Why Not Self-Hosted Analytics on the User's Pi?

- Grafana + Prometheus/InfluxDB are too heavy for a Raspberry Pi running FiestaBoard
- Users shouldn't have to manage an analytics stack
- The project needs aggregated data across all installations, not per-user dashboards
- Local-only analytics wouldn't help the maintainers understand usage patterns

---

## What to Collect

Following Home Assistant's tiered model, FiestaBoard analytics would have two levels:

### Level 1: Basic Analytics (lightweight)

| Data Point | Example | Purpose |
|---|---|---|
| Anonymous installation UUID | `a1b2c3d4-...` | Count unique installations (generated once, stored locally) |
| FiestaBoard version | `1.32.44` | Track adoption of updates |
| Platform | `linux/arm64` | Understand deployment targets |
| Python version | `3.11.2` | Know minimum version to support |
| Board API mode | `local` or `cloud` | Understand connection patterns |
| Uptime (hours) | `168` | Gauge reliability |

### Level 2: Usage Analytics (more detail, still anonymous)

| Data Point | Example | Purpose |
|---|---|---|
| Enabled plugins (names only) | `["weather", "stocks", "muni"]` | Prioritize plugin development |
| Number of pages | `5` | Understand content complexity |
| Number of schedules | `3` | Track schedule feature adoption |
| Template usage (template names) | `["weather_basic", "stocks_ticker"]` | Know which templates are popular |
| Output target | `board`, `ui`, `both` | Understand display preferences |
| Error count (last 24h) | `2` | Track stability |

### What Is NEVER Collected

- API keys or credentials
- Board content or messages
- IP addresses or MAC addresses
- Location data (cities, coordinates, lat/lng)
- Home Assistant entity names, states, or URLs
- WiFi SSIDs or passwords
- Stock symbols or personal configuration values
- Any data that could identify a user, household, or network

---

## Implementation Plan

### Phase 1: Backend Opt-In Infrastructure

**Config addition** — Add an `analytics` section to `config.json`:

```json
{
  "analytics": {
    "enabled": false,
    "level": "basic",
    "installation_id": null
  }
}
```

- `enabled`: Always `false` by default (opt-out)
- `level`: `"basic"` or `"usage"` — controls how much data is shared
- `installation_id`: Auto-generated UUID on first opt-in, stored locally

**Backend module** — New `src/analytics/` module:

- `collector.py` — Gathers metrics from config, plugin registry, pages, schedules
- `sender.py` — Builds the JSON payload and sends it via HTTPS POST (once per day)
- `privacy.py` — Ensures no sensitive data leaks into the payload (validation/filtering)

**Transparency logging** — Before sending, log the exact JSON payload at `INFO` level so users can inspect what was sent.

### Phase 2: Frontend Opt-In UI

**Settings page addition:**

- New "Analytics" card in the Settings page
- Toggle: "Help improve FiestaBoard by sharing anonymous usage data"
- Radio/select: "Basic" or "Usage" level
- "What do we collect?" expandable section explaining each data point
- "Preview payload" button showing the exact JSON that would be sent
- Default state: OFF

### Phase 3: Project-Side Ingest + Dashboard

**Recommended stack for the project server:**

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **Umami** (self-hosted) | MIT license, lightweight, privacy-first, simple dashboard | Needs a small VPS | ~$5/mo VPS |
| **Simple API + SQLite + Grafana** | Full control, minimal dependencies, Grafana dashboards | More custom code to maintain | ~$5/mo VPS |
| **GitHub Pages + JSON** | Zero cost, data stored as JSON files in a repo | No real-time dashboard, manual processing | Free |

**Recommended: Simple API + SQLite + Grafana**

- A minimal FastAPI or Flask endpoint receives the daily POST
- Data is stored in SQLite (lightweight, no DB server needed)
- Grafana reads from SQLite for dashboards
- Hosted on a small VPS or free-tier cloud service
- Total cost: $0-5/month

### Phase 4: Public Dashboard (Optional)

- Like Home Assistant's [analytics.home-assistant.io](https://analytics.home-assistant.io/), publish an aggregated public dashboard
- Shows: total installations, most popular plugins, version distribution
- No individual installation data is ever public

---

## Security Considerations

### Data in Transit
- All telemetry is sent over **HTTPS only**
- The ingest endpoint uses TLS 1.2+
- No sensitive data is included in the payload (defense in depth)

### Data at Rest
- On the user's device: only the installation UUID is stored (in `config.json`)
- On the project server: anonymous data only, 90-day max retention
- SQLite DB access restricted to the project maintainers

### Network Safety (Local Network Concerns)
- Telemetry only sends **outbound** HTTPS requests — no inbound ports opened
- No listening services added to the user's network
- Payload is small (~1KB JSON) — negligible bandwidth
- Sent once per day — no continuous data stream
- If the network blocks outbound requests, the send silently fails (no retries, no errors shown to users)

### Privacy Guarantees
- **No fingerprinting**: The installation UUID is randomly generated, not derived from hardware
- **No tracking across networks**: Moving the Pi to a new network doesn't change behavior
- **No correlation**: The UUID cannot be linked back to a person, household, or network
- **User control**: Opt-out at any time; opting out stops all transmission immediately
- **Data deletion**: If a user opts out, their installation UUID can be removed from the server on request
- **Open source**: The analytics collection and sending code is fully open source and auditable

### Threat Model

| Threat | Mitigation |
|---|---|
| Man-in-the-middle interception | HTTPS/TLS for all transmissions |
| Payload contains sensitive data | Validation layer strips any non-allowlisted fields before sending |
| Server breach exposes user data | Only anonymous UUIDs + version/plugin names stored — no PII |
| Analytics enabled without consent | Default is `false`; requires explicit user action in UI |
| UUID used to track users | UUID is random, not hardware-derived; user can regenerate or delete |

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
       Asked to choose: Basic or Usage level
       "Preview what will be sent" button available

4. User confirms
   └─> installation_id generated (UUID v4)
       analytics.enabled = true written to config.json
       First payload sent after 15 minutes

5. Daily operation
   └─> Once per day, payload is built, logged, and sent via HTTPS
       If send fails, silently retried next day

6. User toggles OFF
   └─> analytics.enabled = false
       No more data collected or sent
       Existing installation_id kept (in case user re-enables)
```

---

## Alternatives Considered

### Grafana on the Pi
- **Rejected**: Too resource-heavy for a Raspberry Pi that's already running FiestaBoard + board communication. Grafana + a time-series DB would add ~500MB RAM usage.

### PostHog Self-Hosted
- **Rejected**: Overkill for this use case. PostHog is designed for product analytics with session replay, feature flags, etc. Too heavy.

### Google Analytics / Mixpanel / Amplitude
- **Rejected**: Third-party services conflict with FiestaBoard's self-hosted ethos. Users may not trust sending data to big tech analytics platforms.

### No Analytics (Status Quo)
- **Rejected**: Without usage data, development decisions are based on guesswork. Knowing which plugins are popular, what platforms are common, and what errors occur helps prioritize work.

---

## Open Questions

1. **Where to host the ingest endpoint?** Options: small VPS, free-tier cloud function (AWS Lambda, Cloudflare Workers), or a GitHub Actions workflow that processes data.
2. **Should there be a public dashboard?** Home Assistant publishes theirs — this builds community trust but requires ongoing maintenance.
3. **Should onboarding prompt for analytics?** Home Assistant asks during setup. FiestaBoard could add an optional prompt on first launch.
4. **Data retention policy?** Proposed 90 days, but could be shorter.

---

## Next Steps

1. **Review this plan** — Get team/community feedback on the approach
2. **Implement Phase 1** — Backend config + collection + sending module
3. **Implement Phase 2** — Settings UI toggle and payload preview
4. **Set up Phase 3** — Deploy ingest endpoint + Grafana dashboard
5. **Document** — Add user-facing docs explaining the analytics feature
