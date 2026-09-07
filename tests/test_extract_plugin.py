"""The registry entry ``scripts/extract_plugin.py`` writes when publishing a plugin.

``extract_plugin`` itself clones, commits and pushes to GitHub, so the piece
worth guarding is the pure translation from a plugin's manifest into its
``plugin-registry.json`` entry — in particular that a transition plugin does
not silently arrive in the marketplace as a data plugin.
"""

from scripts.extract_plugin import FIESTABOARD_VERSION_CONSTRAINT, build_registry_entry

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
        }
