"""Manifest-level integration for the board-preview contract.

The load-safety property matters most here: ``load_manifest`` returns ``None``
whenever validation fails, so an un-migrated plugin must still validate. Absence
means "not migrated yet"; only malformed values are errors.
"""

from src.plugins.manifest import (
    PluginManifest,
    validate_manifest,
    validate_preview_completeness,
)

BASE = {"id": "demo_plugin", "name": "Demo Plugin", "version": "1.0.0"}


def manifest(**overrides) -> dict:
    return {**BASE, **overrides}


class TestLoadSafety:
    """Un-migrated plugins must keep loading."""

    def test_manifest_without_previews_is_valid(self):
        is_valid, errors = validate_manifest(manifest())
        assert is_valid, errors

    def test_manifest_with_only_teaser_is_valid(self):
        is_valid, errors = validate_manifest(manifest(teaser="HELLO"))
        assert is_valid, errors

    def test_manifest_with_only_previews_is_valid(self):
        is_valid, errors = validate_manifest(manifest(previews=[{"device_type": "note", "rows": ["HELLO"]}]))
        assert is_valid, errors


class TestValidationWhenPresent:
    """Malformed values are still errors."""

    def test_oversized_teaser_fails(self):
        is_valid, errors = validate_manifest(manifest(teaser="A" * 16))
        assert not is_valid
        assert any("teaser" in e for e in errors)

    def test_template_variable_in_teaser_fails(self):
        is_valid, errors = validate_manifest(manifest(teaser="{{plugin.value}}"))
        assert not is_valid
        assert any("literal" in e.lower() for e in errors)

    def test_overwide_preview_row_fails(self):
        is_valid, errors = validate_manifest(manifest(previews=[{"device_type": "note", "rows": ["A" * 16]}]))
        assert not is_valid
        assert any("previews[0]" in e for e in errors)

    def test_valid_previews_pass(self):
        is_valid, errors = validate_manifest(
            manifest(
                teaser="{66}AAPL +1.88%",
                previews=[
                    {"device_type": "flagship", "rows": ["A" * 22] * 6},
                    {"device_type": "note", "rows": ["B" * 15] * 3},
                ],
            )
        )
        assert is_valid, errors


class TestTransitionPluginsAreExempt:
    """Transitions have no board content to preview."""

    def test_transition_declaring_teaser_fails(self):
        is_valid, errors = validate_manifest(manifest(plugin_type="transition", teaser="HELLO"))
        assert not is_valid
        assert any("transition" in e for e in errors)

    def test_transition_declaring_previews_fails(self):
        is_valid, errors = validate_manifest(manifest(plugin_type="transition", previews=[{"rows": ["HI"]}]))
        assert not is_valid
        assert any("transition" in e for e in errors)

    def test_transition_without_previews_is_complete(self):
        assert validate_preview_completeness(manifest(plugin_type="transition")) == []


class TestCompletenessLane:
    """The authoring/registry gate is stricter than the load gate."""

    def test_missing_both_reports_both(self):
        errors = validate_preview_completeness(manifest())
        assert len(errors) == 2

    def test_missing_teaser_only(self):
        errors = validate_preview_completeness(manifest(previews=[{"rows": ["HI"]}]))
        assert len(errors) == 1
        assert "teaser" in errors[0]

    def test_complete_manifest_passes(self):
        errors = validate_preview_completeness(manifest(teaser="HI", previews=[{"rows": ["HI"]}]))
        assert errors == []


class TestParsingAndSerialization:
    """from_dict / to_dict round-trip."""

    def test_parses_teaser_and_previews(self):
        parsed = PluginManifest.from_dict(
            manifest(
                teaser="AAPL +1.88%",
                previews=[{"device_type": "note", "rows": ["HELLO"]}],
            )
        )
        assert parsed.teaser == "AAPL +1.88%"
        assert len(parsed.previews) == 1
        assert parsed.previews[0].device_type == "note"

    def test_defaults_are_empty(self):
        parsed = PluginManifest.from_dict(manifest())
        assert parsed.teaser == ""
        assert parsed.previews == []

    def test_to_dict_exposes_previews(self):
        parsed = PluginManifest.from_dict(
            manifest(
                teaser="AAPL",
                previews=[{"device_type": "flagship", "rows": ["HELLO"], "label": "Morning"}],
            )
        )
        result = parsed.to_dict()
        assert result["teaser"] == "AAPL"
        assert result["previews"][0]["label"] == "Morning"
        assert result["previews"][0]["rows"] == ["HELLO"]

    def test_to_dict_fills_default_label(self):
        parsed = PluginManifest.from_dict(manifest(previews=[{"device_type": "flagship", "rows": ["HELLO"]}]))
        assert parsed.to_dict()["previews"][0]["label"] == "Flagship"

    def test_non_string_teaser_is_ignored_at_parse_time(self):
        # validate_manifest rejects it; parsing must not explode.
        parsed = PluginManifest.from_dict(manifest(teaser=42))
        assert parsed.teaser == ""
