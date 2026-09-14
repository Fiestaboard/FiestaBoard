"""The registry entry ``scripts/extract_plugin.py`` writes when publishing a plugin.

``extract_plugin`` itself clones, commits and pushes to GitHub, so the piece
worth guarding is the pure translation from a plugin's manifest into its
``plugin-registry.json`` entry — in particular that a transition plugin does
not silently arrive in the marketplace as a data plugin.
"""

from datetime import date

from scripts.extract_plugin import (
    FIESTABOARD_VERSION_CONSTRAINT,
    build_registry_entry,
    registry_added_date,
)

REPO_URL = "https://github.com/Fiestaboard/fiestaboard-plugin--typewriter"


class TestBuildRegistryEntry:
    def test_carries_transition_plugin_type_from_manifest(self):
        entry = build_registry_entry(
            "typewriter",
            {"name": "Typewriter", "plugin_type": "transition"},
            REPO_URL,
        )
        assert entry["plugin_type"] == "transition"

    def test_defaults_plugin_type_to_data_when_manifest_omits_it(self):
        entry = build_registry_entry("weather", {"name": "Weather"}, REPO_URL)
        assert entry["plugin_type"] == "data"

    def test_carries_manifest_metadata(self):
        entry = build_registry_entry(
            "weather",
            {
                "name": "Weather",
                "description": "Weather data",
                "author": "Alice",
                "icon": "cloud-sun",
                "category": "weather",
            },
            REPO_URL,
            added="2026-03-22",
        )
        assert entry == {
            "id": "weather",
            "name": "Weather",
            "description": "Weather data",
            "repository": REPO_URL,
            "author": "Alice",
            "fiestaboard_version": FIESTABOARD_VERSION_CONSTRAINT,
            "icon": "cloud-sun",
            "category": "weather",
            "plugin_type": "data",
            "added": "2026-03-22",
        }


class TestAddedDate:
    """`added` feeds the marketplace's newness sort (issue #1999)."""

    def test_stamps_today_for_a_new_plugin(self):
        entry = build_registry_entry("weather", {"name": "Weather"}, REPO_URL)
        assert entry["added"] == date.today().isoformat()

    def test_preserves_the_original_date_when_republishing(self):
        """Re-extraction rebuilds the entry, so the old date has to be carried in.

        Without this a plugin re-published years later would jump to the top of
        a newest-first sort as though it had just arrived.
        """
        entry = build_registry_entry("weather", {"name": "Weather"}, REPO_URL, added="2026-03-22")
        assert entry["added"] == "2026-03-22"

    def test_registry_added_date_finds_an_existing_entry(self):
        registry = {"plugins": [{"id": "weather", "added": "2026-03-22"}]}
        assert registry_added_date(registry, "weather") == "2026-03-22"

    def test_registry_added_date_is_empty_for_an_unknown_plugin(self):
        assert registry_added_date({"plugins": []}, "weather") == ""

    def test_registry_added_date_is_empty_for_an_entry_without_one(self):
        registry = {"plugins": [{"id": "weather"}]}
        assert registry_added_date(registry, "weather") == ""
