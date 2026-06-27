"""Tests for the bug-hunt merged-fix collector's pure helpers.

Only the network-free helpers are exercised here (`parse_linked_issues`,
`parse_diff`). `main()` shells out to `gh` and is validated manually via the
learner workflow.
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "gfb", Path(__file__).parent.parent / "gather_fixed_bugs.py"
)
gfb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gfb)


def test_parse_closes_fixes_resolves_and_paren():
    body = "Closes #1273\nalso Fixes #99 and resolves #100\ntitle (#1280)"
    assert sorted(gfb.parse_linked_issues(body)) == [99, 100, 1273, 1280]


def test_parse_dedupes_and_ignores_non_refs():
    assert gfb.parse_linked_issues("no refs here #notanumber") == []
    assert gfb.parse_linked_issues("Closes #5 Closes #5") == [5]


def test_parse_case_insensitive_and_variants():
    assert sorted(gfb.parse_linked_issues("CLOSE #1, fixed #2, RESOLVED #3")) == [1, 2, 3]


def test_parse_handles_empty_and_none():
    assert gfb.parse_linked_issues("") == []
    assert gfb.parse_linked_issues(None) == []


def test_parse_diff_splits_per_file():
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "@@ -1 +1 @@\n-old\n+new\n"
        "diff --git a/bar.py b/bar.py\n"
        "@@ -1 +1 @@\n-x\n+y\n"
    )
    files = gfb.parse_diff(diff)
    assert [f["path"] for f in files] == ["foo.py", "bar.py"]
    assert "+new" in files[0]["patch"]
    assert "+y" in files[1]["patch"]
