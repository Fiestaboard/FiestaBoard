"""Both accessibility themes must run and retain independent failure signals."""

from pathlib import Path

import pytest
import yaml

from tests.ci.workflow_model import run_steps

ROOT = Path(__file__).resolve().parents[2]


def _job():
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]["a11y-tests"]


@pytest.mark.parametrize("failure", [None, "dark_tests", "light_tests"])
def test_both_themes_run_even_when_one_fails(failure):
    ran, failed = run_steps(_job(), failure)
    assert "dark_tests" in ran
    assert "light_tests" in ran
    assert failed == (failure is not None)


def test_no_theme_runs_without_storybook():
    ran, failed = run_steps(_job(), "storybook_server")
    assert failed
    assert "dark_tests" not in ran
    assert "light_tests" not in ran


def test_cancelled_accessibility_job_starts_no_theme():
    ran, _ = run_steps(_job(), cancelled=True)
    assert "dark_tests" not in ran
    assert "light_tests" not in ran
