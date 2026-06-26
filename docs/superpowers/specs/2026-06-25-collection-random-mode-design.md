# Collection Random Mode — Design

**Issue:** [#1287](https://github.com/Fiestaboard/FiestaBoard/issues/1287) — Collection Page Randomizer
**Date:** 2026-06-25

## Problem

A Collection currently shows its pages either in deterministic time order
(`time` mode) or by expression rules (`variable` mode). The user wants a third
option: pick a page **at random** each time the page duration expires, so the
board feels less predictable without building expression rules.

## Decisions

- **Avoid repeats** — random selection must never show the same page twice in a
  row (a "shuffle-bag": every page is shown once before any page repeats). No
  user toggle; this is always-on behavior.
- **Full-stack** — backend logic + API + the web UI Collection mode dropdown.

## Approach: stateless, deterministic shuffle-bag

The existing `time` mode is deterministic and stateless — the active page is a
pure function of the clock (`int(now / interval) % len(pages)`), so it survives
restarts and needs no background loop or stored cursor. Random mode follows the
**same philosophy** rather than a stateful "background RNG", because it fits the
codebase, is restart-safe, and needs zero new storage.

### Algorithm

Let `n = len(page_ids)` and `interval = random.interval_seconds`.

```
bucket = int(now_unix / interval)     # which duration window we are in
round  = bucket // n                  # which full pass through the deck
pos    = bucket % n                   # position within that pass

perm = seeded_permutation(round, n)   # random.Random(round).sample(range(n), n)

# Prevent a repeat across the round boundary: if the first page of this
# round equals the last page of the previous round, swap the first two.
if pos == 0 and round > 0 and n > 1:
    prev_perm = seeded_permutation(round - 1, n)
    if perm[0] == prev_perm[-1]:
        perm[0], perm[1] = perm[1], perm[0]

index = perm[pos]
```

**Why a shuffle-bag and not independent draws:** independent random draws can
repeat (≈1/n per window; 50% for two pages). A per-`round` shuffled permutation
guarantees no repeat *within* a round, and the boundary swap guarantees no
repeat *between* rounds. The result: never the same page twice in a row, with
each page shown equally often.

### Properties

- **Deterministic & stateless:** seeded by integer `round` via `random.Random`,
  which is reproducible across processes/restarts/platforms. No stored cursor.
- **No back-to-back repeats** for `n >= 2`; `n == 1` always returns index 0.
- `seconds_until_next_check` mirrors `time` mode: countdown to the next window
  boundary using `random.interval_seconds`.

## Data model changes (`src/collections/models.py`)

- `SelectionMode = Literal["time", "variable", "random"]`
- New `RandomModeConfig(BaseModel)` with `interval_seconds: int = Field(default=30, ge=5, le=3600)`
  (same constraints as `TimeModeConfig` — this is the "Page Duration").
- `Collection.random: RandomModeConfig | None = None`, defaulting to a config
  when `selection_mode == "random"` (validator-enforced, mirroring `variable`).
- New helpers `current_page_index_random(now_unix)` / `current_page_id_random(now_unix)`.
- `CollectionCreate` / `CollectionUpdate` gain the `random` field.

## Service changes (`src/collections/service.py`)

- `resolve_page_id`: add `selection_mode == "random"` branch →
  `collection.current_page_id_random(ts)`.
- `seconds_until_next_check`: add `random` branch (same math as `time`).
- `create_collection`: pass `random=data.random` through.

## API (`src/api_server.py`)

No new validation logic required — random mode only needs valid `page_ids`,
which `_validate_collection_payload` already enforces. The new `random` field
flows through the existing create/update endpoints via the request models.

## Storage (`src/collections/storage.py`)

Adding an optional `random` field with default `None` is backward-compatible.
Old `collections.json` records load unchanged. **No schema migration needed**
(`CURRENT_SCHEMA_VERSION` stays 1).

## Web (`web/`)

- `web/src/lib/api.ts`: add `"random"` to `CollectionSelectionMode`, a
  `RandomModeConfig` interface, and the `random?` field on `Collection`,
  `CollectionCreate`, `CollectionUpdate`.
- `web/app/routes/collections.tsx`: add a "Random" option to the selection-mode
  dropdown; when selected, show the same interval/duration selector used by time
  mode (writing to `random.interval_seconds`).

## Testing

- **Python (`tests/test_collections.py`):** validator requires `random` config;
  `current_page_index_random` never repeats back-to-back across many buckets,
  is stable within a window, deterministic across calls (restart-safe), and
  handles single-page collections; service `resolve_page_id` and
  `seconds_until_next_check` random branches.
- **Web:** extend the collections type/shape tests for the new mode and config.

## Out of scope

- Per-collection persisted history / weighting.
- Changing `time` or `variable` behavior.
