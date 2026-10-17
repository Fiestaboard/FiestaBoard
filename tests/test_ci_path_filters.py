"""Guard: every repo-root JSON the Python suite reads re-triggers Platform Tests.

Platform Tests in ``.github/workflows/ci.yml`` is gated on the ``api`` /
``shared`` / ``e2e_wiring`` path filters. ``plugin-registry.json`` and
``plugin-previews.json`` were in none of them, so a registry-only PR skipped
the very tests that validate the registry and reported CI Success while
broken (#2004). This test fails if a test module references a repo-root JSON
file that no Platform Tests filter matches.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
TESTS_DIR = REPO_ROOT / "tests"

# Filters whose truthiness runs the Platform Tests job.
PLATFORM_FILTERS = ("api", "shared", "e2e_wiring")


def _path_filters() -> dict[str, list[str]]:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    for step in workflow["jobs"]["detect-changes"]["steps"]:
        if str(step.get("uses", "")).startswith("dorny/paths-filter"):
            return yaml.safe_load(step["with"]["filters"])
    raise AssertionError("dorny/paths-filter step not found in detect-changes")


def _platform_patterns() -> list[str]:
    filters = _path_filters()
    return [pat for name in PLATFORM_FILTERS for pat in filters.get(name, [])]


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def _root_json_read_by_tests() -> set[str]:
    root_json = {p.name for p in REPO_ROOT.glob("*.json")}
    referenced: set[str] = set()
    for test_file in TESTS_DIR.rglob("*.py"):
        text = test_file.read_text(encoding="utf-8")
        for name in root_json:
            if re.search(r"['\"/]" + re.escape(name) + r"['\"]", text):
                referenced.add(name)
    return referenced


def test_platform_tests_gate_matches_its_own_job_condition() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    condition = workflow["jobs"]["test-platform"]["if"]
    for name in PLATFORM_FILTERS:
        assert f"needs.detect-changes.outputs.{name} == 'true'" in condition


def test_registry_files_trigger_platform_tests() -> None:
    patterns = _platform_patterns()
    for name in ("plugin-registry.json", "plugin-previews.json"):
        assert _matches(name, patterns), f"{name} must trigger Platform Tests (#2004)"


def test_every_root_json_read_by_tests_triggers_platform_tests() -> None:
    patterns = _platform_patterns()
    referenced = _root_json_read_by_tests()
    assert "plugin-registry.json" in referenced  # sanity: the scan works
    missing = sorted(n for n in referenced if not _matches(n, patterns))
    assert not missing, (
        f"Tests read {missing} but no Platform Tests path filter "
        f"({', '.join(PLATFORM_FILTERS)}) in ci.yml matches them, so a PR "
        "touching only those files would skip the tests that validate them. "
        "Add them to the `api` filter (#2004)."
    )
