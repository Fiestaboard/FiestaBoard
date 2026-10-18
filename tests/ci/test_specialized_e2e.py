"""Failure-injection checks for the workflow's consolidated E2E wiring."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _job():
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["specialized-e2e-tests"]


def _run_steps(job, failed_step=None, cancelled=False):
    """Evaluate this job's status/outcome expressions with controlled outcomes.

    This deliberately only models our simple conditions, not arbitrary Actions
    expressions. Unknown syntax fails the test instead of assuming reachability.
    """
    outcomes = {}
    failed = False
    ran = []
    for step in job["steps"]:
        expression = str(step.get("if", "success()"))
        expression = expression.removeprefix("${{").removesuffix("}}").strip()
        # Login's event/actor guard is covered by its existing workflow condition;
        # use an internal PR here, for which login is required.
        if step.get("uses", "").startswith("docker/login-action"):
            expression = "success()"
        expression = re.sub(r"steps\.([\w-]+)\.outcome", lambda m: repr(outcomes.get(m[1], "skipped")), expression)
        for token, value in {
            "success()": not failed and not cancelled,
            "failure()": failed,
            "always()": True,
            "cancelled()": cancelled,
        }.items():
            expression = expression.replace(token, str(value))
        expression = expression.replace("&&", " and ").replace("||", " or ")
        expression = re.sub(r"!(?!=)", " not ", expression).strip()
        admitted = eval(expression, {"__builtins__": {}}, {})  # trusted repository YAML only
        identifier = step.get("id", step.get("name"))
        outcome = "skipped"
        if admitted:
            ran.append(identifier)
            outcome = "failure" if identifier == failed_step else "success"
            if outcome == "failure" and not step.get("continue-on-error", False):
                failed = True
        outcomes[identifier] = outcome
    return ran, failed


@pytest.mark.parametrize("failure", [None, "ai_tests", "auth_tests", "ingress_tests", "ai_start", "auth_start"])
def test_suites_remain_independent_and_failures_remain_fatal(failure):
    job = _job()
    ran, failed = _run_steps(job, failure)
    for suite in ("ai", "auth", "ingress"):
        if failure != f"{suite}_start":
            assert f"{suite}_tests" in ran
    assert failed == (failure is not None)
    assert not job.get("continue-on-error", False)


def test_shared_setup_failure_does_not_run_tests_against_missing_environment():
    ran, failed = _run_steps(_job(), "image")
    assert failed
    assert not any(name in ran for name in ("ai_tests", "auth_tests", "ingress_tests"))


def test_cancelled_job_does_not_start_more_suites():
    ran, _ = _run_steps(_job(), cancelled=True)
    assert not any(name in ran for name in ("ai_start", "auth_start", "ingress_start"))


def test_each_suite_keeps_its_own_report_and_artifact():
    steps = _job()["steps"]
    test_steps = [s for s in steps if s.get("id") in ("ai_tests", "auth_tests", "ingress_tests")]
    assert len(test_steps) == 3
    reports = [s["env"]["PLAYWRIGHT_JSON_OUTPUT_FILE"] for s in test_steps]
    assert len(set(reports)) == 3
    for report in reports:
        assert any(f"web/{report}" in s.get("with", {}).get("path", "") for s in steps)
        assert any(f"web/{report}" in s.get("run", "") for s in steps)


def test_combined_suite_is_a_required_success_dependency():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    assert "specialized-e2e-tests" in jobs["ci-success"]["needs"]
