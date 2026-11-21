"""Date-dependent tests fail on their PR; the full integration suite runs nightly on v11.

#2571 added a test that passed only on weekdays and turned UI Tests red on
every PR that weekend. The clock-skew job reruns vitest with the wall clock
started on a Saturday and at a year end (web/src/__tests__/test-now.ts).

The full integration suite otherwise runs only on the Version PR, so its
failures surfaced at release time. nightly-integration.yml dispatches it on v11.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"


def _load(name):
    data = yaml.safe_load((WORKFLOWS / name).read_text())
    # PyYAML parses the bare key `on:` as the boolean True.
    data["on"] = data.get("on", data.pop(True, None))
    return data


def test_clock_skew_job_covers_a_weekend_and_a_year_boundary():
    jobs = _load("ci.yml")["jobs"]
    job = jobs["test-ui-clock-skew"]
    clocks = {c["name"]: c["now"] for c in job["strategy"]["matrix"]["clock"]}
    assert clocks["Saturday"].startswith("2026-11-21T")  # a Saturday
    assert clocks["year end"].startswith("12-31T", 5)
    assert job["strategy"]["fail-fast"] is False
    run = next(s for s in job["steps"] if "TEST_NOW" in s.get("env", {}))
    assert run["env"]["TEST_NOW"] == "${{ matrix.clock.now }}"
    assert "test:run" in run["run"]
    # Same path gate as UI Tests, and a red leg fails CI Success.
    assert job["if"] == jobs["test-ui"]["if"]
    assert "test-ui-clock-skew" in jobs["ci-success"]["needs"]


def test_setup_installs_the_skewed_clock_before_anything_else():
    setup = (ROOT / "web/src/__tests__/setup.ts").read_text()
    first_import = next(line for line in setup.splitlines() if line.startswith("import "))
    assert first_import == 'import "./test-now";'


def test_dispatch_runs_the_full_integration_suite():
    workflow = _load("integration-tests.yml")
    assert "workflow_dispatch" in workflow["on"]
    job = workflow["jobs"]["integration-tests"]
    assert "github.event_name == 'workflow_dispatch') && 'full'" in job["name"]
    for step in job["steps"]:
        name, cond = step.get("name", ""), str(step.get("if", ""))
        if "(full suite" in name:
            assert "github.event_name == 'workflow_dispatch'" in cond, name
        if "(smoke" in name:
            assert "github.event_name == 'pull_request' &&" in cond, name


def test_nightly_dispatches_v11_and_mirrors_the_result():
    workflow = _load("nightly-integration.yml")
    assert workflow["on"]["schedule"][0]["cron"]
    job = workflow["jobs"]["dispatch"]
    assert job["permissions"] == {"actions": "write"}
    assert job["env"]["REF"] == "${{ inputs.ref || 'v11' }}"
    runs = "\n".join(s.get("run", "") for s in job["steps"])
    assert 'gh workflow run integration-tests.yml --ref "$REF"' in runs
    assert "gh run watch" in runs and "--exit-status" in runs
