# Config loss on upgrade (issue #1102, re-run of #948) — design

**Status:** Draft for review
**Issue:** [#1102](https://github.com/Fiestaboard/FiestaBoard/issues/1102) (reopened), prior art [#948](https://github.com/Fiestaboard/FiestaBoard/issues/948)
**Date:** 2026-06-18

## 1. Problem

A user running FiestaBoard under Docker + Watchtower (auto-update + restart on every
new image) loses configuration on each update. The first #1102 fix
(PR #1103, `1416dbec`) addressed only the *startup validator*: it taught
`ConfigManager.validate()` to consult the multi-board settings service so the
backend stops refusing to boot when the legacy `config.json` board block is empty.
That is why **board credentials and the schedule now survive**.

The reopened report is a **different, deeper bug**: after each update the reporter
still loses

- the **board / FiestaBoard name**,
- the **global timezone**, and
- **integrations (plugin selections + their per-plugin configs and API keys)**.

The user has to re-add these by hand after every update.

## 2. Why the loss is selective (key evidence)

Configuration is split across several JSON files, all under the persisted
`./data:/app/data` bind mount:

| Store | Owns | Reporter status |
|---|---|---|
| `data/settings.json` (`SettingsService`, `src/settings/service.py`) | multi-board `boards[]` incl. creds, schedule, mqtt, display, beta | **survives** |
| `data/schedules.json`, `data/pages.json`, `data/collections.json` | scheduler / pages / carousels | **survives** |
| **`data/config.json`** (`ConfigManager`, `src/config_manager.py`) | **`general.timezone`, `plugins.*` (enable + config + secrets), legacy `board` block** | **lost** |

The loss splits **cleanly by file**: everything owned by `config.json` resets;
everything in the other files survives. This rules out the relative-bind-mount
footgun (running `docker compose` from a different directory — documented in
`docker-compose.yml`), which would wipe *all* `data/*.json` files, not just one.
The failure is specific to **`config.json` contents being emptied/reset on a
version change.**

> Note on board name: the per-instance name lives in `settings.json`
> (`boards[].name`), which the reporter says survives. The "name goes blank"
> symptom therefore needs confirmation — it may be the legacy `config.json`
> `board.name`, or a display path that reads the legacy block. The forensic /
> repro step (§5) resolves which store actually owns the blanked name; the
> self-heal (§6) covers both stores regardless.

## 3. This is issue #948 resurfacing

#948 ("Integrations Lost on Upgrade") is the same symptom. Its fix commit
(`db821780`) is explicit that the **root cause was never found**:

> "The exact line that resets the enabled flags between boots remains elusive —
> the 7.0.10..7.1.1 src diff is only ~190 lines and none of it overtly wipes
> configs — but the damage is real and not limited to one user. Stop the bleed
> three ways…"

The #948 evidence: last 7.0.10 boot logged `Initialized 19 plugins (7 enabled)`;
first 7.1.1 boot logged `Initialized 16 plugins (1 enabled)`. Two effects:
plugins extracted to external repos (19→16, the V3 migration) **and** enabled
flags reset (7→1, unexplained).

The three #948 "ways" were **mitigations, not a fix**:

1. **Pre-init snapshot** — `ConfigManager._maybe_snapshot_on_version_change()`
   (`src/config_manager.py:422`) dumps `data/*.json` to
   `data/update-backups/pre-update-<ts>.json` on a version change, *before* any
   merge/migration runs. Captures `config.json, settings.json, pages.json,
   collections.json, schedules.json` (`_PRE_INIT_SNAPSHOT_FILES`, line 414).
2. **Regression hint** — `_detect_post_upgrade_regression()`
   (`src/api_server.py:2099`) warns at startup + via `/system/update/status`.
3. **v2→v3 install retry** — `PluginRegistry._auto_migrate_v2_plugins`.

## 4. The two gaps that matter for #1102

1. **Detection is plugin-only.** `_detect_post_upgrade_regression()` compares
   only the *enabled plugin ID set* (`src/api_server.py:2127–2138`). It does
   **not** detect lost `general.timezone`, lost board name, or a plugin that is
   still "enabled" but lost its API key / config. Two of the three reopened
   complaints aren't even detected today.
2. **Recovery is manual and all-or-nothing.** The user must notice the warning
   and `POST /system/update/rollback` with `restore_settings=true`, which reverts
   *everything* to the snapshot. Most users never do this — they re-run the
   wizard, exactly as the reporter describes.

## 5. Track 1 — Boot diagnostics only (deep hunt deferred)

**Decision:** Track 2 (self-heal) is the primary deliverable, so Track 1 is
scoped to **cheap boundary diagnostics only**. The heavier local-repro harness
and full boot-path audit (5b/5c below) are **deferred** — pursued only if the
self-heal proves insufficient in the wild.

**5a. Boot diagnostics (ships with Track 2).** Log enabled-plugin count +
timezone presence + board-name presence at three boundaries — immediately after
`ConfigManager` load, after settings-service init, after plugin-registry init.
Rationale: this is the safety net for Track 2's blind spot (§6, "empty-snapshot"
case). When the self-heal *can't* recover (the newest snapshot is already
empty), these logs are the only forensic trail explaining why, and they let us
spot the loss boundary if a recurrence is reported. A few log lines, no
behavioral risk.

**5b. (Deferred) Local reproduction harness.** Simulate the upgrade boot in the
dev container by making the running version disagree with `app_version_seen`
(seed `config.json` with enabled plugins + non-default timezone + an older
`app_version_seen`; boot; capture the snapshot, the `Initialized N plugins
(M enabled)` line, and a before/after `config.json` dump). Determines whether the
mechanism is **lost** (recreated empty, `config_manager.py:381`), **corrupted**
(`JSONDecodeError → DEFAULT_CONFIG`, `config_manager.py:374`), or **clobbered in
memory** (file intact, emptied by a migration/merge/settings write-back).

**5c. (Deferred) Boot-path writer audit** of `_load_or_create` /
`_merge_with_defaults` (`config_manager.py:350,557`), `_apply_global_connection`
and settings-service `set_*` during init (`src/settings/service.py:605`), the
plugin registry V2/V3 migration (`src/plugins/registry.py:386–428`), and any
startup `_save_internal()` that could persist a partially-initialized config.

**Trigger to un-defer 5b/5c:** a confirmed recurrence where the diagnostics show
loss but the self-heal could not recover.

## 6. Track 2 — Generalized self-healing auto-restore (PRIMARY)

Take the existing #948 mitigation infrastructure further: **detect a broader
class of regressions and auto-repair them at boot**, instead of only warning
about plugins and waiting for a manual full rollback.

**Scope decision:** detect-and-restore only. A save-boundary write-guard (refuse
to persist a `config.json` materially emptier than what was loaded this boot) was
considered as a second defensive layer and **deferred to §9** — it requires
reliably distinguishing boot-time reconciliation from a user-initiated removal,
which is higher-risk than the restore approach buys us right now.

**Known limitation (the "empty-snapshot" blind spot).** Auto-restore recovers
data only when the loss happens *on the upgrade boot itself* and the same-boot
pre-update snapshot still holds the good values — which matches the #948
evidence and the reported scenario. A user who is **already stuck** (config.json
emptied on a previous boot) has only empty snapshots and cannot be auto-rescued;
they need a one-time manual restore or re-setup. Track 1's diagnostics (§5a)
cover this case forensically. This protects data going *forward* from a good
state; it does not retroactively rescue an already-wiped install.

**6a. Broaden detection.** Generalize `_detect_post_upgrade_regression` into a
structured regression report comparing the newest pre-update snapshot against
live state across:
- `config.json` → `general.timezone` (snapshot non-empty, live empty/default),
- `config.json` → `plugins.*`: enabled-in-snapshot-but-not-live (today's check)
  **plus** plugins that are still enabled but lost config keys (esp.
  `SENSITIVE_FIELDS`),
- `settings.json` → board name (snapshot non-empty, live blank).

**6b. Auto-restore the regressed keys.** When a regression is detected on a
**version-change boot** (i.e. `_maybe_snapshot_on_version_change` fired this
boot), restore **only the regressed keys** from the newest snapshot into the
live stores, save once, and log loudly what was restored.

Why this is safe (the #937 invariant — deliberate uninstalls must not
resurrect): the pre-update snapshot is taken at the **top of this boot's load**,
before any merge/migration, so it reflects the user's *true last-known-good*
state as of the previous version's last run. A plugin the user deliberately
uninstalled under the old version is already absent from that snapshot, so it is
never resurrected. Restoring from the same-boot snapshot targets exactly the
data this boot just dropped.

Guardrails:
- Only run on a detected version change (not on plain restarts).
- Restore only keys that are **present + non-empty in snapshot and
  absent/empty/default in live** — never overwrite a value that still has data.
- Take a fresh backup before writing (reversible), and make it **idempotent**:
  stamp completion so it can't re-run and fight the user on the next boot.
- Restore `config.json` data **before** the plugin registry initializes
  (so enabled flags + configs are in place when `registry.initialize()` reads
  them), or re-initialize the registry after restoring.
- Optional `config.json` flag to disable auto-heal for operators who prefer the
  manual rollback flow.

**6c. Hook point (implementation decision, see §8).** Leading option: perform
the `config.json` restore early in/after `ConfigManager._load_or_create()` —
right after `_maybe_snapshot_on_version_change()` — so the two `config.json`
casualties (timezone, plugins) are healed before any consumer reads them.
Settings.json-owned data (board name) is reconciled in the settings-service
load. Keep the heavy plugin-registry recursion concerns noted at
`config_manager.py:408–440` in mind.

## 7. Testing

- **Track 1 repro** documented as a runnable script/steps (not a committed test
  that depends on `data/`).
- **Detection** unit tests: snapshot-vs-live fixtures for each regression class
  (timezone, plugin enable, plugin config/secret, board name); assert the report
  is empty when live ≥ snapshot.
- **Auto-restore** unit tests: regressed boot restores only the missing keys;
  does **not** resurrect deliberately-removed plugins; does **not** overwrite a
  live value that still has data; is idempotent across two boots; respects the
  disable flag.
- **Guard** the #937 invariant explicitly with a test mirroring the existing
  v2-retry "deliberate uninstall stays uninstalled" case.
- Run via the dev container per CLAUDE.md
  (`docker-compose -f docker-compose.dev.yml exec fiestaboard pytest`).

## 8. Resolved decisions + remaining open items

**Resolved:**
- **Approach** — detect + restore only; Track 1 reduced to diagnostics (§5a).
- **Auto-heal default** — automatic, with a `config.json` flag to disable for
  operators who prefer the manual rollback flow.
- **Branch** — dedicated `fix-1102-config-loss-on-upgrade` (this worktree is on
  an unrelated board-size-indicator branch with no diff vs `main`).

**Still open (settle during the implementation plan):**
- **Restore hook point** — early in `ConfigManager._load_or_create` (simplest
  for the two `config.json` casualties: timezone + plugins) vs a unified
  post-init reconciliation in the api_server lifespan (cleaner cross-store for
  the `settings.json` board name, but must re-init the plugin registry after
  restoring). Leaning toward the early `config.json` restore + a small
  settings-service reconciliation for the name.

## 9. Out of scope / deferred layers

- **Save-boundary write-guard** (deferred). A second defensive layer:
  `ConfigManager._save_internal()` refuses to persist a `config.json` materially
  emptier than what it loaded this boot unless the change is user-initiated.
  More "cure than mask," but the user-vs-boot distinction is the hard part;
  revisit if detect-and-restore proves insufficient.
- **Full store unification** — collapsing `config.json` (timezone/plugins) into
  `SettingsService` for a single load/migrate path. Addresses the class at the
  source but the blast radius (every config reader/writer + a data migration) is
  too large for this fix. Revisit only if the deferred deep hunt (§5b/5c) shows
  the two-store split itself is the root cause.
