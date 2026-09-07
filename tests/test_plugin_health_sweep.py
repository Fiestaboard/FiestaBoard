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


class TestFatalVsAdvisory:
    """Advisory findings must not turn a scheduled run red."""

    def test_fatal_defaults_true(self):
        assert sweep_mod.Finding("p", "install", "x").fatal is True

    def test_advisory_finding_can_be_marked_non_fatal(self):
        assert sweep_mod.Finding("p", "undeclared", "x", fatal=False).fatal is False

    def test_to_dict_carries_the_flag(self):
        assert sweep_mod.Finding("p", "undeclared", "x", fatal=False).to_dict()["fatal"] is False


class TestAgainstRealBundledPlugins:
    """The sweep must find nothing blocking in the plugins we ship."""

    def test_bundled_plugins_sweep_clean(self):

        bundled = PROJECT_ROOT / "plugins"
        if not bundled.exists():
            pytest.skip("bundled plugins not present")
        findings, report = sweep_mod.sweep(bundled, None, do_fetch=False)
        blocking = [f for f in findings if f.fatal]
        assert blocking == [], [f"{f.plugin_id}: {f.detail}" for f in blocking]
        assert report, "sweep discovered no plugins at all"
