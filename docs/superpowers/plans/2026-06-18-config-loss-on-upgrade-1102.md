# Config Loss on Upgrade — Self-Healing Auto-Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a FiestaBoard upgrade boot drops user config (timezone, install name, enabled plugins + their secrets), automatically restore the lost keys from the same-boot pre-update snapshot before the service reads them — no manual rollback.

**Architecture:** All three reported casualties live in `data/config.json` (`general.timezone`, `general.instance_name`, `plugins.*`), already captured by the existing #948 pre-update snapshot (`data/update-backups/pre-update-<ts>.json`). We (1) mark when a boot is a genuine version change, (2) compute which config keys regressed vs the newest snapshot, (3) restore only those keys via `ConfigManager` setters early in the API lifespan — before the plugin registry initializes — then refresh the cached time service. Boot-boundary diagnostics ship alongside as the forensic safety net for the "snapshot already empty" blind spot.

**Tech Stack:** Python 3.11, FastAPI, pytest. No new dependencies.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-18-config-loss-on-upgrade-1102-design.md`. Approach is **detect + restore only** (save-guard and store-unification are deferred, §9).
- **Tests run in the dev container** (CLAUDE.md): `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest <path>`. The dev container must be running (`/start`).
- **No new Python deps**; reuse `_resolve_snapshot_name` / `_list_settings_snapshots` already in `src/api_server.py`.
- **Respect the #937 invariant:** never resurrect a deliberately removed/disabled plugin. Only auto-restore plugins that were **`enabled: True`** in the snapshot.
- **Only act on a genuine version-change boot** (`seen is not None and seen != current`), gated by an env opt-out (`FIESTABOARD_AUTO_RESTORE`, default on).
- **Idempotent & non-destructive:** restore only keys whose snapshot value is meaningful and whose live value is empty/default/missing; never overwrite a live value that still holds data.
- **Branch:** `fix-1102-config-loss-on-upgrade` (already created; spec already committed).
- `src.__version__` is currently `"7.9.0"`. Tests must monkeypatch it rather than hardcode.

---

## File structure

- `src/config_manager.py` — add a `version_changed_on_load` flag set during load (Task 1).
- `src/api_server.py` — add the pure restore-set builder (Task 2), the auto-restore routine (Task 3), wire it into `lifespan` (Task 4), and add boot diagnostics (Task 5).
- `tests/test_config_manager.py` — flag tests (Task 1).
- `tests/test_post_upgrade_restore.py` — new file: builder + auto-restore tests (Tasks 2–3).
- `env.example` — document `FIESTABOARD_AUTO_RESTORE` (Task 3).

---

### Task 1: `ConfigManager.version_changed_on_load` flag

**Files:**
- Modify: `src/config_manager.py` (`__init__` ~line 340, `_maybe_snapshot_on_version_change` ~line 442, add a property)
- Test: `tests/test_config_manager.py`

**Interfaces:**
- Produces: `ConfigManager.version_changed_on_load -> bool` — True only when this process loaded an existing config whose recorded `app_version_seen` was a non-None value different from `src.__version__`. False on fresh installs, corrupt-config resets, and same-version restarts.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config_manager.py` (the autouse `reset_singleton` fixture already isolates the singleton + a tmp settings file):

```python
def test_version_changed_on_load_true_after_upgrade(tmp_path, monkeypatch):
    """An existing config with an older app_version_seen flags a version change."""
    import src

    monkeypatch.setattr(src, "__version__", "9.9.9")
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({"app_version_seen": "1.0.0", "plugins": {"weather": {"enabled": True}}})
    )
    cm = ConfigManager(config_path=str(cfg))
    assert cm.version_changed_on_load is True


def test_version_changed_on_load_false_same_version(tmp_path, monkeypatch):
    """Restart on the same version is not a version change."""
    import src

    monkeypatch.setattr(src, "__version__", "9.9.9")
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"app_version_seen": "9.9.9", "plugins": {}}))
    cm = ConfigManager(config_path=str(cfg))
    assert cm.version_changed_on_load is False


def test_version_changed_on_load_false_fresh_install(tmp_path, monkeypatch):
    """A brand-new config (no file) is not a version change."""
    import src

    monkeypatch.setattr(src, "__version__", "9.9.9")
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    assert cm.version_changed_on_load is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest tests/test_config_manager.py -k version_changed_on_load -v`
Expected: FAIL — `AttributeError: 'ConfigManager' object has no attribute 'version_changed_on_load'`.

- [ ] **Step 3: Initialize the flag in `__init__`**

In `src/config_manager.py`, in `__init__`, add the default immediately before `self._load_or_create()`:

```python
        self._config: dict[str, Any] = {}
        self._raw_features: dict[str, Any] = {}
        self._version_changed_on_load = False
        self._load_or_create()
```

- [ ] **Step 4: Set the flag in `_maybe_snapshot_on_version_change`**

In `_maybe_snapshot_on_version_change`, set the flag right after `seen` is read, before the same-version early return:

```python
        seen = self._config.get(APP_VERSION_SEEN_KEY)
        self._version_changed_on_load = seen is not None and seen != current_version
        if seen == current_version:
            return
```

- [ ] **Step 5: Add the public property**

Add near the other accessors in `ConfigManager`:

```python
    @property
    def version_changed_on_load(self) -> bool:
        """True if this process loaded an existing config from an older app version.

        False on fresh installs, corrupt-config resets, and same-version restarts.
        Drives the post-upgrade auto-restore so it only runs on a real upgrade boot.
        """
        return self._version_changed_on_load
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest tests/test_config_manager.py -k version_changed_on_load -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add src/config_manager.py tests/test_config_manager.py
git commit -m "feat(config): flag version-change boots for post-upgrade auto-restore (#1102)"
```

---

### Task 2: Pure restore-set builder

**Files:**
- Modify: `src/api_server.py` (add function near `_detect_post_upgrade_regression`, ~line 2099)
- Test: `tests/test_post_upgrade_restore.py` (new)

**Interfaces:**
- Consumes: `SENSITIVE_FIELDS` and `DEFAULT_CONFIG` from `src.config_manager`.
- Produces: `_build_post_upgrade_restore_set(snap_config: dict, live_config: dict) -> dict` returning `{"general": {<field>: <snap_value>}, "plugins": {<plugin_id>: <full snap plugin config>}}`. Empty sub-dicts are omitted; an empty result `{}` means nothing regressed.

Rules:
- `general` — for `timezone` and `instance_name` only: include the snapshot value when it is a non-empty string AND the live value differs AND the live value is empty or equal to the `DEFAULT_CONFIG["general"]` default. (A user legitimately on the default is indistinguishable from a wipe-to-default and is intentionally left alone.)
- `plugins` — only plugins with `enabled is True` in the snapshot. Include the **full** snapshot plugin config when the live side lost the enablement (missing plugin, or `enabled` not true) OR lost a sensitive field (a `SENSITIVE_FIELDS` key that is non-empty in the snapshot but empty/missing live).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_post_upgrade_restore.py`:

```python
"""Tests for post-upgrade config auto-restore (#1102 / #948)."""

from src.api_server import _build_post_upgrade_restore_set


def test_restore_set_recovers_timezone_lost_to_default():
    snap = {"general": {"timezone": "America/New_York", "instance_name": "Kitchen"}}
    live = {"general": {"timezone": "America/Los_Angeles", "instance_name": ""}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert result["general"]["timezone"] == "America/New_York"
    assert result["general"]["instance_name"] == "Kitchen"


def test_restore_set_ignores_unchanged_general():
    snap = {"general": {"timezone": "America/New_York", "instance_name": "Kitchen"}}
    live = {"general": {"timezone": "America/New_York", "instance_name": "Kitchen"}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert "general" not in result


def test_restore_set_recovers_disabled_enabled_plugin_with_secrets():
    snap = {"plugins": {"weather": {"enabled": True, "api_key": "real-key", "location": "NYC"}}}
    live = {"plugins": {"weather": {"enabled": False}}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert result["plugins"]["weather"] == snap["plugins"]["weather"]


def test_restore_set_recovers_missing_enabled_plugin():
    snap = {"plugins": {"stocks": {"enabled": True, "finnhub_api_key": "k"}}}
    live = {"plugins": {}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert "stocks" in result["plugins"]


def test_restore_set_recovers_plugin_that_lost_only_its_secret():
    snap = {"plugins": {"weather": {"enabled": True, "openweathermap_api_key": "real"}}}
    live = {"plugins": {"weather": {"enabled": True, "openweathermap_api_key": ""}}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert result["plugins"]["weather"]["openweathermap_api_key"] == "real"


def test_restore_set_does_not_resurrect_disabled_plugin():
    # User deliberately disabled it under the old version -> snapshot has enabled False.
    snap = {"plugins": {"weather": {"enabled": False, "api_key": "real-key"}}}
    live = {"plugins": {}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert result.get("plugins", {}) == {}


def test_restore_set_empty_when_nothing_regressed():
    snap = {"general": {"timezone": "America/New_York"}, "plugins": {"weather": {"enabled": True}}}
    live = {"general": {"timezone": "America/New_York"}, "plugins": {"weather": {"enabled": True}}}
    assert _build_post_upgrade_restore_set(snap, live) == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest tests/test_post_upgrade_restore.py -v`
Expected: FAIL — `ImportError: cannot import name '_build_post_upgrade_restore_set'`.

- [ ] **Step 3: Implement the builder**

In `src/api_server.py`, just above `_detect_post_upgrade_regression` (~line 2099), add:

```python
# Config fields we know are user-set and safe to auto-restore from a snapshot.
_RESTORABLE_GENERAL_FIELDS = ("timezone", "instance_name")


def _build_post_upgrade_restore_set(
    snap_config: dict[str, Any], live_config: dict[str, Any]
) -> dict[str, Any]:
    """Compute which config.json keys regressed vs a pre-update snapshot.

    Returns ``{"general": {...}, "plugins": {...}}`` with only the keys worth
    restoring; an empty dict means nothing regressed. See plan Task 2 for rules.
    """
    from src.config_manager import DEFAULT_CONFIG, SENSITIVE_FIELDS

    result: dict[str, Any] = {}

    snap_general = snap_config.get("general") or {}
    live_general = live_config.get("general") or {}
    default_general = DEFAULT_CONFIG.get("general", {})
    general: dict[str, Any] = {}
    for field in _RESTORABLE_GENERAL_FIELDS:
        snap_val = snap_general.get(field)
        if not isinstance(snap_val, str) or not snap_val:
            continue
        live_val = live_general.get(field)
        if live_val == snap_val:
            continue
        if live_val in ("", None, default_general.get(field)):
            general[field] = snap_val
    if general:
        result["general"] = general

    snap_plugins = snap_config.get("plugins") or {}
    live_plugins = live_config.get("plugins") or {}
    plugins: dict[str, Any] = {}
    for pid, snap_cfg in snap_plugins.items():
        if not (isinstance(snap_cfg, dict) and snap_cfg.get("enabled") is True):
            continue  # only auto-restore plugins the user had ENABLED (#937 invariant)
        live_cfg = live_plugins.get(pid)
        lost_enable = not (isinstance(live_cfg, dict) and live_cfg.get("enabled") is True)
        lost_secret = isinstance(live_cfg, dict) and any(
            key in SENSITIVE_FIELDS and snap_cfg.get(key) and not live_cfg.get(key)
            for key in snap_cfg
        )
        if lost_enable or lost_secret:
            plugins[pid] = snap_cfg
    if plugins:
        result["plugins"] = plugins

    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest tests/test_post_upgrade_restore.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/api_server.py tests/test_post_upgrade_restore.py
git commit -m "feat(upgrade): detect regressed config keys vs pre-update snapshot (#1102)"
```

---

### Task 3: Auto-restore routine (apply the restore set)

**Files:**
- Modify: `src/api_server.py` (new function after `_build_post_upgrade_restore_set`)
- Modify: `env.example`
- Test: `tests/test_post_upgrade_restore.py`

**Interfaces:**
- Consumes: `get_config_manager()`, `_resolve_snapshot_name`, `_build_post_upgrade_restore_set`, `reset_time_service`, `ConfigManager.version_changed_on_load` (Task 1), `ConfigManager.set_general` / `set_plugin_config` / `get_all`.
- Produces: `_auto_restore_post_upgrade_regression() -> dict[str, Any]` — returns a summary dict (`{"general": [...field names...], "plugins": [...plugin ids...]}`) of what it restored, or `{}` when it did nothing. Side effects: writes restored keys into `config.json` and resets the cached time service.

Gating order: (1) env opt-out, (2) not a version-change boot, (3) no readable newest snapshot, (4) empty restore set → each returns `{}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_post_upgrade_restore.py`:

```python
import json
from unittest.mock import MagicMock

import src.api_server as api_server


def _seed_snapshot(tmp_path, config_payload):
    snap = tmp_path / "pre-update-20260101T000000.000Z.json"
    snap.write_text(json.dumps({"data": {"config": config_payload}}))
    return snap


def test_auto_restore_applies_general_and_plugins(tmp_path, monkeypatch):
    snap_path = _seed_snapshot(
        tmp_path,
        {
            "general": {"timezone": "America/New_York", "instance_name": "Kitchen"},
            "plugins": {"weather": {"enabled": True, "api_key": "real"}},
        },
    )
    cm = MagicMock()
    cm.version_changed_on_load = True
    cm.get_all.return_value = {
        "general": {"timezone": "America/Los_Angeles", "instance_name": ""},
        "plugins": {"weather": {"enabled": False}},
    }
    monkeypatch.setattr(api_server, "get_config_manager", lambda: cm)
    monkeypatch.setattr(api_server, "_resolve_snapshot_name", lambda name=None: snap_path)
    reset_called = MagicMock()
    monkeypatch.setattr(api_server, "reset_time_service", reset_called)
    monkeypatch.delenv("FIESTABOARD_AUTO_RESTORE", raising=False)

    summary = api_server._auto_restore_post_upgrade_regression()

    cm.set_general.assert_called_once()
    assert cm.set_general.call_args[0][0] == {
        "timezone": "America/New_York",
        "instance_name": "Kitchen",
    }
    cm.set_plugin_config.assert_called_once_with("weather", {"enabled": True, "api_key": "real"})
    reset_called.assert_called_once()
    # summary lists are sorted() -> alphabetical
    assert summary == {"general": ["instance_name", "timezone"], "plugins": ["weather"]}


def test_auto_restore_noop_when_not_version_change(tmp_path, monkeypatch):
    cm = MagicMock()
    cm.version_changed_on_load = False
    monkeypatch.setattr(api_server, "get_config_manager", lambda: cm)
    monkeypatch.delenv("FIESTABOARD_AUTO_RESTORE", raising=False)
    assert api_server._auto_restore_post_upgrade_regression() == {}
    cm.set_general.assert_not_called()


def test_auto_restore_noop_when_disabled_by_env(tmp_path, monkeypatch):
    cm = MagicMock()
    cm.version_changed_on_load = True
    monkeypatch.setattr(api_server, "get_config_manager", lambda: cm)
    monkeypatch.setenv("FIESTABOARD_AUTO_RESTORE", "0")
    assert api_server._auto_restore_post_upgrade_regression() == {}
    cm.set_general.assert_not_called()


def test_auto_restore_noop_when_nothing_regressed(tmp_path, monkeypatch):
    snap_path = _seed_snapshot(
        tmp_path, {"general": {"timezone": "America/New_York"}, "plugins": {}}
    )
    cm = MagicMock()
    cm.version_changed_on_load = True
    cm.get_all.return_value = {"general": {"timezone": "America/New_York"}, "plugins": {}}
    monkeypatch.setattr(api_server, "get_config_manager", lambda: cm)
    monkeypatch.setattr(api_server, "_resolve_snapshot_name", lambda name=None: snap_path)
    monkeypatch.setattr(api_server, "reset_time_service", MagicMock())
    monkeypatch.delenv("FIESTABOARD_AUTO_RESTORE", raising=False)
    assert api_server._auto_restore_post_upgrade_regression() == {}
    cm.set_general.assert_not_called()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest tests/test_post_upgrade_restore.py -k auto_restore -v`
Expected: FAIL — `AttributeError: module 'src.api_server' has no attribute '_auto_restore_post_upgrade_regression'`.

- [ ] **Step 3: Confirm the time-service import is available in `api_server`**

Check that `reset_time_service` is importable in `src/api_server.py`. Run:
`grep -n "reset_time_service" src/api_server.py`
If absent, add to the imports near the other `from .time_service` / service imports at the top of the module:

```python
from .time_service import reset_time_service  # noqa: E402
```

(The tests monkeypatch `api_server.reset_time_service`, so it must be a module-level name.)

- [ ] **Step 4: Implement the routine**

In `src/api_server.py`, immediately after `_build_post_upgrade_restore_set`, add:

```python
def _auto_restore_post_upgrade_regression() -> dict[str, Any]:
    """Restore config keys lost on an upgrade boot from the newest pre-update
    snapshot, before the service/registry reads config. Returns a summary of
    what was restored (empty when it did nothing). See issue #1102 / #948.
    """
    if os.environ.get("FIESTABOARD_AUTO_RESTORE", "1").strip().lower() in ("0", "false", "no"):
        return {}

    cm = get_config_manager()
    if not getattr(cm, "version_changed_on_load", False):
        return {}

    newest = _resolve_snapshot_name(None)
    if newest is None:
        return {}
    try:
        snap_doc = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    snap_config = (snap_doc.get("data") or {}).get("config") or {}
    if not snap_config:
        return {}

    restore_set = _build_post_upgrade_restore_set(snap_config, cm.get_all())
    if not restore_set:
        return {}

    summary: dict[str, Any] = {}
    general = restore_set.get("general")
    if general:
        cm.set_general(general)
        summary["general"] = sorted(general)
    plugins = restore_set.get("plugins")
    if plugins:
        for pid, cfg in plugins.items():
            cm.set_plugin_config(pid, cfg)
        summary["plugins"] = sorted(plugins)

    # Restored timezone won't take effect until the cached TimeService is rebuilt.
    reset_time_service()
    return summary
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest tests/test_post_upgrade_restore.py -v`
Expected: PASS (11 passed).

- [ ] **Step 6: Document the env var in `env.example`**

Add to `env.example` (near other `FIESTABOARD_*` entries):

```bash
# Auto-restore config (timezone, install name, enabled plugins + secrets) from the
# pre-update snapshot when an upgrade boot is detected to have dropped it (#1102/#948).
# Set to 0 to disable and rely on manual /system/update/rollback instead.
FIESTABOARD_AUTO_RESTORE=1
```

- [ ] **Step 7: Commit**

```bash
git add src/api_server.py tests/test_post_upgrade_restore.py env.example
git commit -m "feat(upgrade): auto-restore config lost on upgrade from snapshot (#1102)"
```

---

### Task 4: Wire auto-restore into the API lifespan

**Files:**
- Modify: `src/api_server.py` (`lifespan`, ~lines 677–691)

**Interfaces:**
- Consumes: `_auto_restore_post_upgrade_regression` (Task 3), existing `_detect_post_upgrade_regression`.

The restore must run **before** `get_service()` (~line 694) so the plugin registry reads the restored config. The existing warning-only hint remains as a fallback for when auto-restore is disabled or could not recover (empty snapshot).

- [ ] **Step 1: Insert the auto-restore call before the hint block**

In `src/api_server.py`, directly above the existing `try:`/`_regression_hint = _detect_post_upgrade_regression()` block (~line 677), add:

```python
    # Auto-heal config dropped on an upgrade boot (#1102/#948) BEFORE the
    # service + plugin registry read it. No-op unless this is a version-change
    # boot with a snapshot that still holds the lost data.
    try:
        _restored = _auto_restore_post_upgrade_regression()
        if _restored:
            logger.warning("Post-upgrade auto-restore applied from snapshot: %s", _restored)
    except Exception:  # pragma: no cover - safety net must never block boot
        logger.debug("Post-upgrade auto-restore failed", exc_info=True)
```

Leave the existing `_detect_post_upgrade_regression` hint block in place immediately after — once auto-restore succeeds it will report no regression, but it still fires when auto-restore is disabled or the snapshot was already empty.

- [ ] **Step 2: Verify the module imports cleanly**

Run: `docker-compose -f docker-compose.dev.yml exec fiestaboard python -c "import src.api_server"`
Expected: no output, exit 0.

- [ ] **Step 3: Run the full new test file + the config-manager flag tests**

Run: `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest tests/test_post_upgrade_restore.py tests/test_config_manager.py -v`
Expected: PASS (all).

- [ ] **Step 4: Commit**

```bash
git add src/api_server.py
git commit -m "feat(upgrade): run config auto-restore on startup before service init (#1102)"
```

---

### Task 5: Boot-boundary diagnostics (Track 1 safety net)

**Files:**
- Modify: `src/api_server.py` (helper + two call sites in `lifespan`)

**Interfaces:**
- Produces: `_log_config_boot_snapshot(stage: str) -> None` — logs enabled-plugin count, timezone, and install-name presence at a named boot stage. Pure logging; never raises.

Rationale: when the snapshot is already empty (the documented blind spot), auto-restore can't recover and these logs are the only forensic trail. Cheap, no behavioral risk.

- [ ] **Step 1: Implement the diagnostics helper**

In `src/api_server.py`, near the other startup helpers, add:

```python
def _log_config_boot_snapshot(stage: str) -> None:
    """Log a one-line config fingerprint at a boot stage (issue #1102 forensics)."""
    try:
        cm = get_config_manager()
        general = cm.get_general()
        plugins = cm.get_all_plugin_configs()
        enabled = sum(1 for c in plugins.values() if isinstance(c, dict) and c.get("enabled"))
        logger.info(
            "config boot snapshot [%s]: %d plugin(s), %d enabled, timezone=%r, instance_name=%r",
            stage,
            len(plugins),
            enabled,
            general.get("timezone"),
            general.get("instance_name"),
        )
    except Exception:  # pragma: no cover - diagnostics must never block boot
        logger.debug("config boot snapshot [%s] failed", stage, exc_info=True)
```

- [ ] **Step 2: Add call sites in `lifespan`**

Call it once right after the auto-restore block (post-restore state) and once after the service is initialized (`get_service()` returns, ~line 694+):

```python
    _log_config_boot_snapshot("post-restore")
```

and, after the auto-start service block:

```python
    _log_config_boot_snapshot("post-service-init")
```

- [ ] **Step 3: Verify import + boot log wiring**

Run: `docker-compose -f docker-compose.dev.yml exec fiestaboard python -c "import src.api_server"`
Expected: exit 0.

- [ ] **Step 4: Restart the dev container and confirm the lines appear**

Run: `docker-compose -f docker-compose.dev.yml restart fiestaboard && docker-compose -f docker-compose.dev.yml logs --since 1m fiestaboard | grep "config boot snapshot"`
Expected: two `config boot snapshot [post-restore]` / `[post-service-init]` lines.

- [ ] **Step 5: Commit**

```bash
git add src/api_server.py
git commit -m "chore(upgrade): log config fingerprint at boot stages for #1102 forensics"
```

---

### Task 6: End-to-end verification in the dev container

**Files:** none (manual verification + final commit of any notes)

- [ ] **Step 1: Simulate an upgrade that wipes config**

With the dev container running, craft a snapshot + a wiped live config, then restart:

```bash
# 1. Capture current state, then seed a pre-update snapshot with rich data
#    and an emptied live config to mimic the upgrade-time loss.
docker-compose -f docker-compose.dev.yml exec fiestaboard sh -c '
  mkdir -p data/update-backups
  cat > data/update-backups/pre-update-20260101T000000.000Z.json <<"EOF"
{"data":{"config":{"general":{"timezone":"America/New_York","instance_name":"Kitchen"},
"plugins":{"weather":{"enabled":true,"openweathermap_api_key":"demo-key"}}}}}
EOF
  python - <<"EOF"
import json,sys
p="data/config.json"
c=json.load(open(p))
c["app_version_seen"]="0.0.1"               # force a version-change boot
c.setdefault("general",{})["timezone"]="America/Los_Angeles"  # wiped to default
c["general"]["instance_name"]=""
c["plugins"]={"weather":{"enabled":False}}  # enablement + secret lost
json.dump(c,open(p,"w"),indent=2)
print("seeded wiped config")
EOF'
```

- [ ] **Step 2: Restart and observe auto-restore**

Run: `docker-compose -f docker-compose.dev.yml restart fiestaboard && docker-compose -f docker-compose.dev.yml logs --since 1m fiestaboard | grep -iE "auto-restore|config boot snapshot"`
Expected: a `Post-upgrade auto-restore applied from snapshot: {'general': ['instance_name', 'timezone'], 'plugins': ['weather']}` line, and the `post-restore` fingerprint showing 1 enabled plugin + `timezone='America/New_York'` + `instance_name='Kitchen'`.

- [ ] **Step 3: Confirm the restore persisted to disk**

Run: `docker-compose -f docker-compose.dev.yml exec fiestaboard python -c "import json; c=json.load(open('data/config.json')); print(c['general']['timezone'], repr(c['general']['instance_name']), c['plugins']['weather'])"`
Expected: `America/New_York 'Kitchen' {'enabled': True, 'openweathermap_api_key': 'demo-key'}`.

- [ ] **Step 4: Confirm idempotency on a same-version restart**

Run: `docker-compose -f docker-compose.dev.yml restart fiestaboard && docker-compose -f docker-compose.dev.yml logs --since 1m fiestaboard | grep -i "auto-restore" || echo "no restore on same-version restart (expected)"`
Expected: no auto-restore line (version unchanged → `version_changed_on_load` False).

- [ ] **Step 5: Run the full affected test suites once more**

Run: `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest tests/test_post_upgrade_restore.py tests/test_config_manager.py -v`
Expected: PASS.

- [ ] **Step 6: Restore your own dev data (cleanup)**

Remove the simulated snapshot so it doesn't shadow real ones:

```bash
docker-compose -f docker-compose.dev.yml exec fiestaboard rm -f data/update-backups/pre-update-20260101T000000.000Z.json
```

---

## Notes for the PR

- Closes the reopened half of #1102 (timezone / install name / integrations lost on upgrade); generalizes the #948 mitigation from "warn + manual rollback" to "auto-restore the regressed keys."
- Deferred (see spec §9): save-boundary write-guard, full `config.json`/`settings.json` store unification, and the heavy local-repro/boot-path root-cause audit (un-defer if diagnostics show a recurrence the snapshot can't recover).
- `settings.json` board name (`boards[].name`) is NOT auto-restored here — the reported "FiestaBoard name" maps to `config.json` `general.instance_name`, which IS covered. If a recurrence shows the per-board name regressing too, extend `_build_post_upgrade_restore_set` to a `settings` category using the same snapshot (which already captures `settings.json`).
