"""Tests for install-time plugin validation.

The anchor case is the Star Trek Quotes regression: a plugin whose data file
was never shipped, which passed its own CI because CI created the file, and
served "???" to every user. `test_catches_the_star_trek_regression` encodes
that exact shape.
"""

import json
from pathlib import Path

import pytest

from src.plugins.install_check import (
    InstallCheckResult,
    check_declaration_is_well_formed,
    check_declared_data_files,
    check_dependencies,
    check_required_files,
    detect_data_file_problems,
    validate_install,
)
from src.plugins.manifest import PluginManifest, parse_data_files


def make_plugin_dir(tmp_path: Path, plugin_id: str, manifest_extra: dict | None = None, files: dict | None = None):
    """Create a plugin directory and return (dir, parsed manifest)."""
    plugin_dir = tmp_path / plugin_id
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text("class Plugin:\n    pass\n")
    manifest_data = {
        "id": plugin_id,
        "name": plugin_id,
        "version": "1.0.0",
        **(manifest_extra or {}),
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest_data))
    for name, content in (files or {}).items():
        target = plugin_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return plugin_dir, PluginManifest.from_dict(manifest_data)


class TestParseDataFiles:
    def test_keeps_plain_relative_paths(self):
        assert parse_data_files(["quotes.json", "data/extra.csv"]) == [
            "quotes.json",
            "data/extra.csv",
        ]

    def test_drops_absolute_paths(self):
        assert parse_data_files(["/etc/passwd"]) == []

    def test_drops_parent_traversal(self):
        assert parse_data_files(["../../src/utils/quotes.json"]) == []

    def test_drops_windows_style_escapes(self):
        assert parse_data_files(["..\\..\\secrets.json", "C:/data.json"]) == []

    def test_normalises_leading_dot_slash(self):
        assert parse_data_files(["./quotes.json"]) == ["quotes.json"]

    def test_dedupes(self):
        assert parse_data_files(["quotes.json", "./quotes.json"]) == ["quotes.json"]

    def test_ignores_non_list_and_non_string(self):
        assert parse_data_files("quotes.json") == []
        assert parse_data_files(None) == []
        assert parse_data_files([1, None, {}]) == []

    def test_manifest_exposes_parsed_declaration(self):
        m = PluginManifest.from_dict({"id": "p", "name": "p", "version": "1.0.0", "data_files": ["quotes.json"]})
        assert m.data_files == ["quotes.json"]

    def test_manifest_without_declaration_defaults_empty(self):
        m = PluginManifest.from_dict({"id": "p", "name": "p", "version": "1.0.0"})
        assert m.data_files == []


class TestDeclaredDataFiles:
    def test_missing_declared_file_is_an_error(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p")
        errors = check_declared_data_files(plugin_dir, ["quotes.json"])
        assert len(errors) == 1
        assert "quotes.json" in errors[0]

    def test_present_declared_file_is_clean(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p", files={"quotes.json": "{}"})
        assert check_declared_data_files(plugin_dir, ["quotes.json"]) == []

    def test_nested_declared_file_is_supported(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p", files={"data/quotes.json": "{}"})
        assert check_declared_data_files(plugin_dir, ["data/quotes.json"]) == []

    def test_directory_where_a_file_was_declared_is_an_error(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p")
        (plugin_dir / "quotes.json").mkdir()
        errors = check_declared_data_files(plugin_dir, ["quotes.json"])
        assert len(errors) == 1
        assert "not a file" in errors[0]


class TestDeclarationWellFormed:
    def test_escaping_entry_is_reported(self):
        raw = {"data_files": ["../../src/utils/quotes.json"]}
        errors = check_declaration_is_well_formed(raw, parse_data_files(raw["data_files"]))
        assert len(errors) == 1
        assert "inside the plugin directory" in errors[0]

    def test_valid_entries_are_silent(self):
        raw = {"data_files": ["quotes.json"]}
        assert check_declaration_is_well_formed(raw, parse_data_files(raw["data_files"])) == []

    def test_non_string_entry_is_reported(self):
        raw = {"data_files": [123]}
        errors = check_declaration_is_well_formed(raw, parse_data_files(raw["data_files"]))
        assert len(errors) == 1
        assert "not a string" in errors[0]

    def test_absent_declaration_is_silent(self):
        assert check_declaration_is_well_formed({}, []) == []


class TestDependencies:
    def test_uninstallable_dependency_is_an_error(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p", files={"requirements.txt": "definitely-not-a-real-package\n"})
        errors = check_dependencies(plugin_dir)
        assert len(errors) == 1
        assert "definitely-not-a-real-package" in errors[0]

    def test_platform_provided_dependency_is_clean(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p", files={"requirements.txt": "requests>=2.0\n"})
        assert check_dependencies(plugin_dir) == []

    def test_dev_requirements_are_ignored(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(
            tmp_path, "p", files={"requirements-dev.txt": "definitely-not-a-real-package\n"}
        )
        assert check_dependencies(plugin_dir) == []

    def test_comments_and_blanks_are_ignored(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(
            tmp_path,
            "p",
            files={"requirements.txt": "# comment\n\n   \nrequests  # inline\n"},
        )
        assert check_dependencies(plugin_dir) == []

    def test_distribution_name_is_mapped_to_import_name(self, tmp_path):
        """speedtest-cli imports as 'speedtest'; a naive guess would say speedtest_cli."""
        plugin_dir, _ = make_plugin_dir(tmp_path, "p", files={"requirements.txt": "speedtest-cli\n"})
        errors = check_dependencies(plugin_dir)
        assert len(errors) == 1
        assert "speedtest-cli" in errors[0]

    @pytest.mark.parametrize("dist", ["finnhub-python", "paho-mqtt"])
    def test_shipped_dist_with_a_different_import_name_is_clean(self, tmp_path, dist):
        """A package FiestaBoard ships must never be reported as missing.

        Both of these are in the platform's own requirements.txt and both
        import under a name that is not their distribution name
        (``finnhub``, ``paho.mqtt``). Resolving them by guessing the import
        name reports them absent, which at install time is not a warning --
        it refuses the install of a plugin whose dependency is in fact
        present. Neither appears in IMPORT_NAME_OVERRIDES, so the guess is
        the only thing standing between them and a false rejection.
        """
        plugin_dir, _ = make_plugin_dir(tmp_path, "p", files={"requirements.txt": f"{dist}\n"})
        assert check_dependencies(plugin_dir) == []

    def test_no_requirements_file_is_clean(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p")
        assert check_dependencies(plugin_dir) == []


class TestRequiredFiles:
    def test_missing_init_is_an_error(self, tmp_path):
        plugin_dir = tmp_path / "p"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.json").write_text("{}")
        errors = check_required_files(plugin_dir)
        assert any("__init__.py" in e for e in errors)

    def test_complete_plugin_is_clean(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p")
        assert check_required_files(plugin_dir) == []


class TestValidateInstall:
    def test_catches_the_star_trek_regression(self, tmp_path):
        """A plugin declaring a data file it does not ship must be rejected."""
        plugin_dir, manifest = make_plugin_dir(
            tmp_path, "star_trek_quotes", manifest_extra={"data_files": ["quotes.json"]}
        )
        result = validate_install("star_trek_quotes", plugin_dir, manifest)
        assert result.ok is False
        assert any("quotes.json" in e for e in result.errors)

    def test_same_plugin_passes_once_the_file_ships(self, tmp_path):
        plugin_dir, manifest = make_plugin_dir(
            tmp_path,
            "star_trek_quotes",
            manifest_extra={"data_files": ["quotes.json"]},
            files={"quotes.json": '{"tng": []}'},
        )
        result = validate_install("star_trek_quotes", plugin_dir, manifest)
        assert result.ok is True, result.errors
        assert result.errors == []

    def test_plugin_reading_no_files_is_clean_and_silent(self, tmp_path):
        """Most plugins read nothing off disk; they must not be nagged."""
        plugin_dir, manifest = make_plugin_dir(tmp_path, "weather")
        result = validate_install("weather", plugin_dir, manifest)
        assert result.ok is True
        assert result.warnings == []

    def test_undeclared_but_present_read_warns_without_blocking(self, tmp_path):
        """Reads a file, declares nothing, but the file does ship."""
        plugin_dir, manifest = make_plugin_dir(tmp_path, "legacy", files={"quotes.json": "{}"})
        (plugin_dir / "__init__.py").write_text('from pathlib import Path\nD = Path(__file__).parent / "quotes.json"\n')
        result = validate_install("legacy", plugin_dir, manifest)
        assert result.ok is True, "a present file must not block an install"
        assert any("does not declare it" in w for w in result.warnings)

    def test_undeclared_and_missing_read_is_blocking(self, tmp_path):
        """The Star Trek case, which declared nothing: must still be caught."""
        plugin_dir, manifest = make_plugin_dir(tmp_path, "star_trek_quotes")
        (plugin_dir / "__init__.py").write_text(
            'from pathlib import Path\nplugin_dir = Path(__file__).parent\nquotes = plugin_dir / "quotes.json"\n'
        )
        result = validate_install("star_trek_quotes", plugin_dir, manifest)
        assert result.ok is False, "an undeclared missing file is still broken"
        assert any("quotes.json" in e for e in result.errors)

    def test_declared_read_produces_no_warning(self, tmp_path):
        plugin_dir, manifest = make_plugin_dir(
            tmp_path,
            "tidy",
            manifest_extra={"data_files": ["quotes.json"]},
            files={"quotes.json": "{}"},
        )
        (plugin_dir / "__init__.py").write_text('from pathlib import Path\nD = Path(__file__).parent / "quotes.json"\n')
        result = validate_install("tidy", plugin_dir, manifest)
        assert result.ok is True
        assert result.warnings == []

    def test_transition_plugin_is_not_nagged_about_data_files(self, tmp_path):
        plugin_dir, manifest = make_plugin_dir(tmp_path, "typewriter", manifest_extra={"plugin_type": "transition"})
        result = validate_install("typewriter", plugin_dir, manifest)
        assert result.ok is True
        assert result.warnings == []

    def test_missing_directory_is_an_error(self, tmp_path):
        result = validate_install("ghost", tmp_path / "nope", None)
        assert result.ok is False
        assert "does not exist" in result.errors[0]

    def test_unparseable_manifest_is_an_error(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p")
        result = validate_install("p", plugin_dir, None)
        assert result.ok is False
        assert any("could not be parsed" in e for e in result.errors)

    def test_errors_accumulate_rather_than_short_circuit(self, tmp_path):
        """One run should tell the author everything that is wrong."""
        plugin_dir, manifest = make_plugin_dir(
            tmp_path,
            "messy",
            manifest_extra={"data_files": ["a.json", "b.json"]},
            files={"requirements.txt": "definitely-not-a-real-package\n"},
        )
        result = validate_install("messy", plugin_dir, manifest)
        assert result.ok is False
        assert len(result.errors) == 3  # two missing files + one missing dep

    def test_result_serialises(self, tmp_path):
        plugin_dir, manifest = make_plugin_dir(tmp_path, "p", files={"quotes.json": "{}"})
        result = validate_install("p", plugin_dir, manifest)
        assert set(result.to_dict()) == {"errors", "warnings"}


class TestDataFileProblemSeverity:
    """Severity tracks whether the plugin can work, not whether it declared.

    This is the rule the first refactor got wrong: moving detection under the
    declaration downgraded the Star Trek case (which declared nothing) from
    broken to advisory.
    """

    def _plugin_with_source(self, tmp_path, source, files=None):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p", files=files)
        (plugin_dir / "__init__.py").write_text(source)
        return plugin_dir

    READS_DATA = 'from pathlib import Path\nD = Path(__file__).parent / "data.json"\n'
    READS_VIA_VAR = (
        'from pathlib import Path\nplugin_dir = Path(__file__).parent\nquotes = plugin_dir / "quotes.json"\n'
    )
    ESCAPES = 'from pathlib import Path\nD = Path(__file__).parent.parent.parent / "src" / "utils" / "q.json"\n'

    def test_missing_and_undeclared_is_an_error(self, tmp_path):
        """The exact Star Trek shape: reads it, declares nothing, ships nothing."""
        d = self._plugin_with_source(tmp_path, self.READS_VIA_VAR)
        errors, warnings = detect_data_file_problems(d, [])
        assert len(errors) == 1, warnings
        assert "quotes.json" in errors[0]
        assert warnings == []

    def test_missing_and_declared_is_an_error(self, tmp_path):
        d = self._plugin_with_source(tmp_path, self.READS_DATA)
        errors, _ = detect_data_file_problems(d, ["data.json"])
        assert len(errors) == 1

    def test_present_but_undeclared_is_only_a_warning(self, tmp_path):
        d = self._plugin_with_source(tmp_path, self.READS_DATA, files={"data.json": "{}"})
        errors, warnings = detect_data_file_problems(d, [])
        assert errors == []
        assert len(warnings) == 1
        assert "does not declare it" in warnings[0]

    def test_present_and_declared_is_silent(self, tmp_path):
        d = self._plugin_with_source(tmp_path, self.READS_DATA, files={"data.json": "{}"})
        assert detect_data_file_problems(d, ["data.json"]) == ([], [])

    def test_escaping_path_is_an_error(self, tmp_path):
        d = self._plugin_with_source(tmp_path, self.ESCAPES)
        errors, _ = detect_data_file_problems(d, [])
        assert len(errors) == 1
        assert "outside the plugin directory" in errors[0]

    def test_escape_cannot_be_silenced_by_declaring_it(self, tmp_path):
        d = self._plugin_with_source(tmp_path, self.ESCAPES)
        errors, warnings = detect_data_file_problems(d, ["src/utils/q.json"])
        assert len(errors) == 1
        assert warnings == []

    def test_manifest_json_is_never_reported(self, tmp_path):
        d = self._plugin_with_source(
            tmp_path, 'from pathlib import Path\nM = Path(__file__).parent / "manifest.json"\n'
        )
        assert detect_data_file_problems(d, []) == ([], [])

    def test_nested_module_reaching_its_package_root_is_allowed(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p", files={"data.json": "{}"})
        lib = plugin_dir / "lib"
        lib.mkdir()
        (lib / "loader.py").write_text('from pathlib import Path\nD = Path(__file__).parent.parent / "data.json"\n')
        assert detect_data_file_problems(plugin_dir, ["data.json"]) == ([], [])

    def test_test_files_are_not_scanned(self, tmp_path):
        plugin_dir, _ = make_plugin_dir(tmp_path, "p")
        tests = plugin_dir / "tests"
        tests.mkdir()
        (tests / "test_x.py").write_text('from pathlib import Path\nF = Path(__file__).parent / "fixture.json"\n')
        assert detect_data_file_problems(plugin_dir, []) == ([], [])

    def test_same_file_reported_once(self, tmp_path):
        d = self._plugin_with_source(
            tmp_path,
            "from pathlib import Path\n"
            "plugin_dir = Path(__file__).parent\n"
            'a = plugin_dir / "data.json"\n'
            'b = Path(__file__).parent / "data.json"\n',
        )
        errors, warnings = detect_data_file_problems(d, [])
        assert len(errors) + len(warnings) == 1


class TestAgainstRealBundledPlugins:
    """Shipped plugins must pass their own gate."""

    @pytest.mark.parametrize("plugin_id", ["date_time", "countdown", "random", "typewriter"])
    def test_bundled_plugin_installs_clean(self, plugin_id):
        from src.plugins.manifest import load_manifest

        plugin_dir = Path(__file__).resolve().parent.parent / "plugins" / plugin_id
        if not plugin_dir.exists():
            pytest.skip(f"{plugin_id} not present")
        manifest, manifest_errors = load_manifest(plugin_dir / "manifest.json")
        assert manifest is not None, manifest_errors
        result = validate_install(plugin_id, plugin_dir, manifest)
        assert result.ok is True, result.errors


class TestInstallCheckResult:
    def test_ok_is_false_only_for_errors(self):
        r = InstallCheckResult("p", warnings=["just a note"])
        assert r.ok is True
        r.errors.append("real problem")
        assert r.ok is False
