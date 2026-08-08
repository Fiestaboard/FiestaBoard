"""The plugin-previews seed and its sync merge rules.

Two things are guarded here:

1. The committed ``plugin-previews.json`` stays complete and valid - every
   registry plugin has an entry with a valid teaser and both a flagship and a
   note preview, so the docs site is never missing a board.

2. ``sync_plugin_previews.sync`` preserves the design's resolution order:
   manifest values win, seed entries are the fallback, entries disappear only
   when a plugin leaves the registry, and an invalid or half-adopted manifest
   declaration never regresses an existing entry.
"""

import json
from pathlib import Path

from scripts.sync_plugin_previews import manifest_entry, sync
from src.plugins.previews import validate_previews, validate_teaser

REPO_ROOT = Path(__file__).parent.parent

SEED = json.loads((REPO_ROOT / "plugin-previews.json").read_text())
REGISTRY = json.loads((REPO_ROOT / "plugin-registry.json").read_text())

VALID_ENTRY = {
    "teaser": "{66}AAPL +1.88%",
    "previews": [{"device_type": "note", "rows": ["STOCKS", "AAPL +1.88%"]}],
}


class TestSeedIntegrity:
    def test_every_registry_plugin_has_an_entry(self):
        registry_ids = {plugin["id"] for plugin in REGISTRY["plugins"]}
        missing = registry_ids - set(SEED["plugins"])
        assert not missing, f"registry plugins missing from plugin-previews.json: {sorted(missing)}"

    def test_no_orphan_entries(self):
        registry_ids = {plugin["id"] for plugin in REGISTRY["plugins"]}
        orphans = set(SEED["plugins"]) - registry_ids
        assert not orphans, f"plugin-previews.json entries not in the registry: {sorted(orphans)}"

    def test_every_teaser_is_valid(self):
        for plugin_id, entry in SEED["plugins"].items():
            errors = validate_teaser(entry["teaser"])
            assert not errors, f"{plugin_id}: {errors}"

    def test_every_previews_list_is_valid(self):
        for plugin_id, entry in SEED["plugins"].items():
            errors = validate_previews(entry["previews"])
            assert not errors, f"{plugin_id}: {errors}"

    def test_every_entry_covers_flagship_and_note(self):
        """The #1436 requirement: Note owners see a preview too."""
        for plugin_id, entry in SEED["plugins"].items():
            devices = {preview.get("device_type", "flagship") for preview in entry["previews"]}
            assert {"flagship", "note"} <= devices, f"{plugin_id} covers only {sorted(devices)}"

    def test_entries_are_sorted(self):
        assert list(SEED["plugins"]) == sorted(SEED["plugins"])


def registry_of(*plugin_ids: str) -> dict:
    return {"plugins": [{"id": plugin_id} for plugin_id in plugin_ids]}


def seed_of(**entries: dict) -> dict:
    return {"version": 1, "plugins": entries}


class TestManifestEntry:
    def test_no_manifest_returns_none(self):
        assert manifest_entry("demo", None) is None

    def test_manifest_without_fields_returns_none(self):
        assert manifest_entry("demo", {"id": "demo"}) is None

    def test_valid_declaration_is_adopted(self):
        entry = manifest_entry("demo", {"id": "demo", **VALID_ENTRY})
        assert entry == VALID_ENTRY

    def test_teaser_without_previews_is_rejected(self, capsys):
        assert manifest_entry("demo", {"id": "demo", "teaser": "HELLO"}) is None
        assert "without previews" in capsys.readouterr().err

    def test_invalid_teaser_is_rejected(self):
        declaration = {**VALID_ENTRY, "teaser": "THIS TEASER IS FAR TOO LONG FOR A NOTE"}
        assert manifest_entry("demo", {"id": "demo", **declaration}) is None

    def test_invalid_previews_are_rejected(self):
        declaration = {**VALID_ENTRY, "previews": [{"device_type": "spaceship", "rows": ["HI"]}]}
        assert manifest_entry("demo", {"id": "demo", **declaration}) is None

    def test_unknown_preview_keys_are_stripped(self):
        declaration = {
            "teaser": "HELLO",
            "previews": [{"device_type": "note", "rows": ["HELLO"], "screenshot": "x.png"}],
        }
        entry = manifest_entry("demo", {"id": "demo", **declaration})
        assert entry is not None
        assert "screenshot" not in entry["previews"][0]


class TestSyncMerge:
    def test_manifest_wins_over_seed(self):
        seed = seed_of(demo={"teaser": "OLD", "previews": []})
        result = sync(registry_of("demo"), seed, {"demo": {"id": "demo", **VALID_ENTRY}})
        assert result["plugins"]["demo"] == VALID_ENTRY

    def test_seed_preserved_without_manifest_fields(self):
        seed = seed_of(demo=VALID_ENTRY)
        result = sync(registry_of("demo"), seed, {"demo": {"id": "demo"}})
        assert result["plugins"]["demo"] == VALID_ENTRY

    def test_seed_preserved_when_manifest_fetch_failed(self):
        seed = seed_of(demo=VALID_ENTRY)
        result = sync(registry_of("demo"), seed, {"demo": None})
        assert result["plugins"]["demo"] == VALID_ENTRY

    def test_seed_preserved_when_manifest_declaration_invalid(self):
        seed = seed_of(demo=VALID_ENTRY)
        bad = {"id": "demo", "teaser": "X" * 40, "previews": VALID_ENTRY["previews"]}
        result = sync(registry_of("demo"), seed, {"demo": bad})
        assert result["plugins"]["demo"] == VALID_ENTRY

    def test_entry_removed_when_plugin_leaves_registry(self):
        seed = seed_of(demo=VALID_ENTRY, gone=VALID_ENTRY)
        result = sync(registry_of("demo"), seed, {"demo": None})
        assert "gone" not in result["plugins"]

    def test_new_plugin_without_anything_warns_but_does_not_crash(self, capsys):
        result = sync(registry_of("brand_new"), seed_of(), {"brand_new": {"id": "brand_new"}})
        assert result["plugins"] == {}
        assert "no manifest previews and no seed entry" in capsys.readouterr().err

    def test_output_is_sorted(self):
        seed = seed_of(zebra=VALID_ENTRY, aardvark=VALID_ENTRY)
        result = sync(registry_of("zebra", "aardvark"), seed, {})
        assert list(result["plugins"]) == ["aardvark", "zebra"]

    def test_non_plugin_keys_survive(self):
        seed = {"_comment": "hello", "version": 1, "plugins": {"demo": VALID_ENTRY}}
        result = sync(registry_of("demo"), seed, {})
        assert result["_comment"] == "hello"
        assert result["version"] == 1
