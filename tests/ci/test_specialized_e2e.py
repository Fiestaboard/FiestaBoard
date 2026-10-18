"""Failure-injection checks for the workflow's consolidated E2E wiring."""

from pathlib import Path

import pytest
import yaml

from tests.ci.workflow_model import run_steps

ROOT = Path(__file__).resolve().parents[2]


def _job():
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["specialized-e2e-tests"]


@pytest.mark.parametrize("failure", [None, "ai_tests", "auth_tests", "ingress_tests", "ai_start", "auth_start"])
def test_suites_remain_independent_and_failures_remain_fatal(failure):
    job = _job()
    ran, failed = run_steps(job, failure)
    for suite in ("ai", "auth", "ingress"):
        if failure != f"{suite}_start":
            assert f"{suite}_tests" in ran
    assert failed == (failure is not None)
    assert not job.get("continue-on-error", False)


def test_shared_setup_failure_does_not_run_tests_against_missing_environment():
    ran, failed = run_steps(_job(), "image")
    assert failed
    assert not any(name in ran for name in ("ai_tests", "auth_tests", "ingress_tests"))


def test_cancelled_job_does_not_start_more_suites():
    ran, _ = run_steps(_job(), cancelled=True)
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
