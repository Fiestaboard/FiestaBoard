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


SCRIPT = "bash scripts/ci/clock-skew-tests.sh"


def _script():
    return (ROOT / "scripts/ci/clock-skew-tests.sh").read_text()


def test_clock_skew_instants_are_a_saturday_and_a_year_end_in_utc():
    script = _script()
    assert '"2026-11-21T12:00:00Z 2026-12-31T23:00:00Z"' in script  # Sat; Dec 31
    assert "export TZ=UTC" in script
    # The shim is checked under each instant before the suite runs.
    assert "src/__tests__/test-now.test.ts" in script


def test_pr_job_is_one_runner_with_changed_tests_and_full_suite_triggers():
    jobs = _load("ci.yml")["jobs"]
    job = jobs["test-ui-clock-skew"]
    assert "strategy" not in job, "one job: one npm ci, both instants back to back"
    assert job["env"]["TZ"] == "UTC"
    checkout = job["steps"][0]
    assert checkout["with"]["fetch-depth"] == 0, "--changed needs the base branch"
    run = next(s for s in job["steps"] if s.get("run") == SCRIPT)
    assert run["env"]["BASE_REF"] == "${{ github.base_ref }}"
    script = _script()
    assert '--changed "origin/$BASE_REF"' in script
    assert "changeset-release/*" in script
    for trigger in ("setup|test-now", "(vitest|vite)\\.config", "mocks/"):
        assert trigger in script, trigger
    # Same path gate as UI Tests, and a red run fails CI Success.
    assert job["if"] == jobs["test-ui"]["if"]
    assert "test-ui-clock-skew" in jobs["ci-success"]["needs"]


def test_nightly_dispatch_runs_the_full_clock_skew_suite():
    job = _load("integration-tests.yml")["jobs"]["clock-skew-full"]
    assert job["if"] == "github.event_name == 'workflow_dispatch'"
    assert job["env"] == {"TZ": "UTC", "CLOCK_SKEW_MODE": "full"}
    assert any(s.get("run") == SCRIPT for s in job["steps"])


def test_dispatches_are_never_cancelled_by_concurrency():
    concurrency = _load("integration-tests.yml")["concurrency"]
    assert concurrency["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"
    assert "github.run_id" in concurrency["group"]


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
    # The run to watch: the id gh prints, else a dispatch by this job's token.
    assert "/actions/runs/[0-9]+" in runs
    assert "--user 'github-actions[bot]'" in runs
    assert "gh run watch" in runs and "--exit-status" in runs
