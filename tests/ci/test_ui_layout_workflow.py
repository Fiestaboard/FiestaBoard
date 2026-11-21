"""The browser layout suite runs in its own sharded job, never inside UI Tests.

UI Tests used to run vitest coverage (8-14 min) and then the serial layout
suite (8-11 min) on one runner under a 25-minute limit; the bug bash grew the
layout suite until the job was cancelled at "Browser layout regressions".
These checks keep the two apart, keep every shard running, and keep the
layout result fatal for CI Success.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LAYOUT_CONFIG = "tests/layout/playwright.config.ts"


def _jobs():
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]


def _runs(job):
    return [step.get("run", "") for step in job.get("steps", [])]


def test_ui_tests_no_longer_runs_the_layout_suite():
    assert not any(LAYOUT_CONFIG in run for run in _runs(_jobs()["test-ui"]))


def test_layout_suite_has_its_own_job_covering_every_shard():
    job = _jobs()["test-ui-layout"]
    shards = job["strategy"]["matrix"]["shard"]
    total = len(shards)
    assert total >= 2
    assert sorted(shards) == list(range(1, total + 1))
    # One failing shard must not cancel the others' evidence.
    assert job["strategy"]["fail-fast"] is False
    layout_steps = [step for step in job["steps"] if LAYOUT_CONFIG in step.get("run", "")]
    assert len(layout_steps) == 1
    assert '--shard="$LAYOUT_SHARD"' in layout_steps[0]["run"]
    assert layout_steps[0]["env"]["LAYOUT_SHARD"] == f"${{{{ matrix.shard }}}}/{total}"
    # Room for a shard of the serial suite plus setup, well clear of the old 25.
    assert 10 <= job["timeout-minutes"] <= 20


def test_layout_job_runs_whenever_ui_tests_would():
    jobs = _jobs()
    assert jobs["test-ui-layout"]["if"] == jobs["test-ui"]["if"]
    assert jobs["test-ui-layout"]["needs"] == jobs["test-ui"]["needs"]


def test_each_shard_keeps_its_own_evidence_artifact():
    steps = _jobs()["test-ui-layout"]["steps"]
    uploads = [s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact")]
    names = [s["with"]["name"] for s in uploads]
    assert any("matrix.shard" in name for name in names)
    assert all(s.get("if") == "always()" for s in uploads)


def test_ci_success_waits_for_the_layout_job():
    assert "test-ui-layout" in _jobs()["ci-success"]["needs"]
