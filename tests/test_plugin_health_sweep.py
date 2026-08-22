"""Tests for scripts/plugin_health_sweep.py.

Each test builds a synthetic plugin directory exhibiting one real failure
mode and asserts the sweep catches it -- and, just as importantly, that a
healthy plugin produces no findings, so the checks cannot pass by flagging
everything.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SWEEP_PATH = PROJECT_ROOT / "scripts" / "plugin_health_sweep.py"


def _load_sweep_module():
    spec = importlib.util.spec_from_file_location("plugin_health_sweep", SWEEP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["plugin_health_sweep"] = module
    spec.loader.exec_module(module)
    return module


sweep_mod = _load_sweep_module()


HEALTHY_SOURCE = """
import json
from pathlib import Path


class Plugin:
    def __init__(self, manifest):
        self.manifest = manifest
        data_file = Path(__file__).parent / "data.json"
        self._data = json.loads(data_file.read_text())
"""

# The Star Trek Quotes shape: reads a file that does not ship, then reaches
# back out of the plugin directory for a platform-owned copy.
ESCAPING_SOURCE = """
import json
from pathlib import Path


class Plugin:
    def __init__(self, manifest):
        quotes_file = Path(__file__).parent / "quotes.json"
        if not quotes_file.exists():
            quotes_file = Path(__file__).parent.parent.parent / "src" / "utils" / "quotes.json"
        self._data = json.loads(quotes_file.read_text())
"""


def make_plugin(tmp_path: Path, plugin_id: str, source: str, files: dict | None = None):
    """Create a plugin directory on disk."""
    plugin_dir = tmp_path / plugin_id
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(source)
    (plugin_dir / "manifest.json").write_text(json.dumps({"id": plugin_id, "name": plugin_id, "version": "1.0.0"}))
    for name, content in (files or {}).items():
        target = plugin_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return plugin_dir


class TestDataFileCheck:
    def test_flags_data_file_that_does_not_ship(self, tmp_path):
        plugin_dir = make_plugin(tmp_path, "brokenplug", HEALTHY_SOURCE)
        findings = sweep_mod.check_data_files("brokenplug", plugin_dir)
        assert len(findings) == 1
        assert findings[0].check == "data_files"
        assert "data.json" in findings[0].detail

    def test_flags_a_missing_file_reached_through_a_variable(self, tmp_path):
        """Exactly how star_trek_quotes spells it, and how most plugins do."""
        source = (
            'from pathlib import Path\n\nplugin_dir = Path(__file__).parent\nquotes_file = plugin_dir / "quotes.json"\n'
        )
        plugin_dir = make_plugin(tmp_path, "varplug", source)
        findings = sweep_mod.check_data_files("varplug", plugin_dir)
        assert len(findings) == 1
        assert "quotes.json" in findings[0].detail

    def test_passes_when_the_data_file_ships(self, tmp_path):
        plugin_dir = make_plugin(tmp_path, "goodplug", HEALTHY_SOURCE, {"data.json": "{}"})
        assert sweep_mod.check_data_files("goodplug", plugin_dir) == []

    def test_ignores_manifest_json(self, tmp_path):
        source = 'from pathlib import Path\np = Path(__file__).parent / "manifest.json"\n'
        plugin_dir = make_plugin(tmp_path, "manifestonly", source)
        assert sweep_mod.check_data_files("manifestonly", plugin_dir) == []

    def test_ignores_plugins_without_file_references(self, tmp_path):
        source = "import requests\n\n\nclass Plugin:\n    pass\n"
        plugin_dir = make_plugin(tmp_path, "netplug", source)
        assert sweep_mod.check_data_files("netplug", plugin_dir) == []

    def test_does_not_scan_test_files(self, tmp_path):
        plugin_dir = make_plugin(tmp_path, "withtests", HEALTHY_SOURCE, {"data.json": "{}"})
        tests_dir = plugin_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_x.py").write_text(
            'from pathlib import Path\nfixture = Path(__file__).parent / "fixture.json"\n'
        )
        assert sweep_mod.check_data_files("withtests", plugin_dir) == []


class TestSelfContainedCheck:
    def test_flags_path_escaping_the_plugin_directory(self, tmp_path):
        """The exact Star Trek Quotes regression."""
        plugin_dir = make_plugin(tmp_path, "escaper", ESCAPING_SOURCE)
        findings = sweep_mod.check_self_contained("escaper", plugin_dir)
        assert len(findings) == 1
        assert findings[0].check == "self_contained"
        assert "escaping the plugin directory" in findings[0].detail

    def test_escape_is_flagged_even_when_the_file_happens_to_exist(self, tmp_path):
        """A path that resolves on this box still breaks on a real install."""
        plugin_dir = make_plugin(tmp_path, "luckyescaper", ESCAPING_SOURCE)
        stray = tmp_path.parent / "src" / "utils"
        stray.mkdir(parents=True, exist_ok=True)
        (stray / "quotes.json").write_text("{}")
        findings = sweep_mod.check_self_contained("luckyescaper", plugin_dir)
        assert len(findings) == 1

    def test_allows_paths_inside_the_plugin_directory(self, tmp_path):
        plugin_dir = make_plugin(tmp_path, "selfcontained", HEALTHY_SOURCE, {"data.json": "{}"})
        assert sweep_mod.check_self_contained("selfcontained", plugin_dir) == []

    def test_allows_a_nested_module_reaching_its_own_package_root(self, tmp_path):
        """plugins/<id>/lib/loader.py reading ../data.json is fine."""
        plugin_dir = make_plugin(tmp_path, "nested", "class Plugin:\n    pass\n", {"data.json": "{}"})
        lib = plugin_dir / "lib"
        lib.mkdir()
        (lib / "loader.py").write_text('from pathlib import Path\nDATA = Path(__file__).parent.parent / "data.json"\n')
        assert sweep_mod.check_self_contained("nested", plugin_dir) == []


class TestDependencyCheck:
    def test_flags_a_dependency_that_is_not_installed(self, tmp_path):
        plugin_dir = make_plugin(
            tmp_path,
            "needsdep",
            HEALTHY_SOURCE,
            {"data.json": "{}", "requirements.txt": "definitely-not-installed>=1.0\n"},
        )
        findings = sweep_mod.check_dependencies("needsdep", plugin_dir)
        assert len(findings) == 1
        assert findings[0].check == "dependencies"
        assert "definitely-not-installed" in findings[0].detail

    def test_passes_for_a_dependency_the_platform_ships(self, tmp_path):
        plugin_dir = make_plugin(
            tmp_path,
            "usesrequests",
            HEALTHY_SOURCE,
            {"data.json": "{}", "requirements.txt": "requests>=2.0\n"},
        )
        assert sweep_mod.check_dependencies("usesrequests", plugin_dir) == []

    def test_ignores_comments_and_blank_lines(self, tmp_path):
        plugin_dir = make_plugin(
            tmp_path,
            "commented",
            HEALTHY_SOURCE,
            {
                "data.json": "{}",
                "requirements.txt": "# a comment\n\n  \nrequests>=2.0  # inline\n",
            },
        )
        assert sweep_mod.check_dependencies("commented", plugin_dir) == []

    def test_maps_distribution_names_to_import_names(self, tmp_path):
        """speedtest-cli imports as 'speedtest', not 'speedtest_cli'."""
        assert sweep_mod.IMPORT_NAME_OVERRIDES["speedtest-cli"] == "speedtest"
        plugin_dir = make_plugin(
            tmp_path,
            "speedy",
            HEALTHY_SOURCE,
            {"data.json": "{}", "requirements.txt": "speedtest-cli\n"},
        )
        findings = sweep_mod.check_dependencies("speedy", plugin_dir)
        assert len(findings) == 1
        assert "'speedtest'" in findings[0].detail

    def test_skips_dev_requirements(self, tmp_path):
        plugin_dir = make_plugin(
            tmp_path,
            "devonly",
            HEALTHY_SOURCE,
            {"data.json": "{}", "requirements-dev.txt": "definitely-not-installed\n"},
        )
        assert sweep_mod.check_dependencies("devonly", plugin_dir) == []


class TestFetchContract:
    class _Result:
        def __init__(self, available, error=None, data=None):
            self.available = available
            self.error = error
            self.data = data

    class _Plugin:
        def __init__(self, behaviour):
            self.behaviour = behaviour
            self.config = {}

        def get_settings_schema(self):
            return {"properties": {"refresh_seconds": {"default": 300}}}

        def fetch_data(self):
            return self.behaviour()

    def test_raising_fetch_is_a_finding(self):
        def boom():
            raise RuntimeError("upstream exploded")

        findings, status = sweep_mod.check_fetch_contract("p", self._Plugin(boom))
        assert status == "FETCH_RAISED"
        assert len(findings) == 1
        assert "upstream exploded" in findings[0].detail

    def test_returning_none_is_a_finding(self):
        findings, status = sweep_mod.check_fetch_contract("p", self._Plugin(lambda: None))
        assert status == "RETURNED_NONE"
        assert len(findings) == 1

    def test_unavailable_without_a_reason_is_a_finding(self):
        plugin = self._Plugin(lambda: self._Result(False, error="  "))
        findings, status = sweep_mod.check_fetch_contract("p", plugin)
        assert status == "SILENT_UNAVAILABLE"
        assert len(findings) == 1

    def test_unavailable_with_a_reason_is_reported_but_not_a_finding(self):
        """An unconfigured plugin is normal and must not fail the sweep."""
        plugin = self._Plugin(lambda: self._Result(False, error="Not configured"))
        findings, status = sweep_mod.check_fetch_contract("p", plugin)
        assert status == "UNAVAILABLE"
        assert findings == []

    def test_available_is_clean(self):
        plugin = self._Plugin(lambda: self._Result(True, data={"x": 1}))
        findings, status = sweep_mod.check_fetch_contract("p", plugin)
        assert status == "OK"
        assert findings == []

    def test_schema_defaults_always_enable_the_plugin(self):
        plugin = self._Plugin(lambda: self._Result(True))
        config = sweep_mod.schema_defaults(plugin)
        assert config["enabled"] is True
        assert config["refresh_seconds"] == 300


class TestReferencedDataPaths:
    def test_counts_parent_hops(self):
        refs = sweep_mod.referenced_data_paths('p = Path(__file__).parent.parent.parent / "src" / "x.json"')
        assert refs == [(3, ["src", "x.json"])]

    def test_handles_os_path_join(self):
        refs = sweep_mod.referenced_data_paths('p = os.path.join(os.path.dirname(__file__), "data.json")')
        assert refs == [(1, ["data.json"])]

    def test_ignores_non_data_suffixes(self):
        refs = sweep_mod.referenced_data_paths('p = Path(__file__).parent / "helper.py"')
        assert refs == []

    def test_ignores_paths_not_anchored_to_file(self):
        refs = sweep_mod.referenced_data_paths('p = Path("/etc/config.json")')
        assert refs == []

    def test_follows_an_anchor_held_in_a_variable(self):
        """The idiomatic two-line spelling must not slip past the check."""
        refs = sweep_mod.referenced_data_paths(
            'plugin_dir = Path(__file__).parent\nquotes = plugin_dir / "quotes.json"\n'
        )
        assert refs == [(1, ["quotes.json"])]

    def test_follows_a_variable_anchor_with_parent_hops(self):
        refs = sweep_mod.referenced_data_paths(
            'root = Path(__file__).parent.parent.parent\ndata = root / "src" / "utils" / "x.json"\n'
        )
        assert refs == [(3, ["src", "utils", "x.json"])]

    def test_follows_a_variable_anchor_through_os_path_join(self):
        refs = sweep_mod.referenced_data_paths(
            'here = os.path.dirname(__file__)\ndata = os.path.join(here, "data.json")\n'
        )
        assert refs == [(1, ["data.json"])]

    def test_reports_a_file_referenced_twice_only_once(self):
        refs = sweep_mod.referenced_data_paths(
            "plugin_dir = Path(__file__).parent\n"
            'a = plugin_dir / "data.json"\n'
            'b = Path(__file__).parent / "data.json"\n'
        )
        assert refs == [(1, ["data.json"])]


class TestFindingSerialisation:
    def test_to_dict_round_trips(self):
        finding = sweep_mod.Finding("plug", "data_files", "missing x.json")
        assert finding.to_dict() == {
            "plugin": "plug",
            "check": "data_files",
            "detail": "missing x.json",
            "fatal": True,
        }


class TestMarkdownReport:
    def test_clean_sweep_says_so(self):
        body = sweep_mod.render_markdown([], [{"plugin": "a"}], Path("/ext"))
        assert "No breakage found" in body
        assert "Swept **1** plugins" in body

    def test_findings_are_grouped_by_plugin(self):
        findings = [
            sweep_mod.Finding("alpha", "data_files", "missing a.json"),
            sweep_mod.Finding("alpha", "self_contained", "escapes dir"),
            sweep_mod.Finding("beta", "dependencies", "needs feedparser"),
        ]
        body = sweep_mod.render_markdown(findings, [{}, {}], Path("/ext"))
        assert "### `alpha`" in body
        assert "### `beta`" in body
        assert body.index("### `alpha`") < body.index("### `beta`")
        assert "**3** issue(s) across **2** plugin(s)" in body

    def test_explains_only_the_checks_that_fired(self):
        findings = [sweep_mod.Finding("alpha", "dependencies", "needs x")]
        body = sweep_mod.render_markdown(findings, [{}], Path("/ext"))
        assert "**dependencies**:" in body
        assert "**self_contained**:" not in body


class TestSetOutput:
    def test_writes_to_github_output_when_present(self, tmp_path, monkeypatch):
        output = tmp_path / "gh_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        sweep_mod.set_output("has_findings", "true")
        assert output.read_text() == "has_findings=true\n"

    def test_is_a_noop_outside_actions(self, monkeypatch):
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        sweep_mod.set_output("has_findings", "true")  # must not raise


class TestAgainstRealBundledPlugins:
    """The sweep must find nothing wrong with the plugins we actually ship."""

    @pytest.mark.parametrize("plugin_id", ["date_time", "countdown", "random", "typewriter"])
    def test_bundled_plugin_is_clean(self, plugin_id):
        plugin_dir = PROJECT_ROOT / "plugins" / plugin_id
        if not plugin_dir.exists():
            pytest.skip(f"{plugin_id} not present")
        findings = (
            sweep_mod.check_data_files(plugin_id, plugin_dir)
            + sweep_mod.check_self_contained(plugin_id, plugin_dir)
            + sweep_mod.check_dependencies(plugin_id, plugin_dir)
        )
        assert findings == [], [f.detail for f in findings]
