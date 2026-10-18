"""Exercise the final CI gate with failures that must block merging."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/check_results.py"


def _needs():
    return {
        "detect-changes": {
            "result": "success",
            "outputs": {"image_formats_result": "success", "structure_result": "success"},
        },
        "test-platform": {"result": "success"},
        "test-ui": {"result": "success"},
    }


def _check(needs):
    return subprocess.run(
        [sys.executable, str(SCRIPT)], input=json.dumps(needs), capture_output=True, text=True, timeout=5
    )


@pytest.mark.parametrize("result", ["failure", "cancelled", "", "unknown"])
def test_nonpassing_job_blocks_ci(result):
    needs = _needs()
    needs["test-platform"]["result"] = result
    run = _check(needs)
    assert run.returncode == 1
    assert "test-platform" in run.stdout + run.stderr


@pytest.mark.parametrize("check", ["image_formats_result", "structure_result"])
@pytest.mark.parametrize("result", ["failure", "cancelled", "", None])
def test_preflight_failure_or_missing_output_blocks_ci(check, result):
    needs = _needs()
    if result is None:
        del needs["detect-changes"]["outputs"][check]
    else:
        needs["detect-changes"]["outputs"][check] = result
    assert _check(needs).returncode == 1


def test_unconditional_image_check_cannot_be_skipped():
    needs = _needs()
    needs["detect-changes"]["outputs"]["image_formats_result"] = "skipped"
    assert _check(needs).returncode == 1


def test_docs_only_changes_can_skip_structure_and_unrelated_suites():
    needs = _needs()
    needs["detect-changes"]["outputs"]["structure_result"] = "skipped"
    needs["test-ui"]["result"] = "skipped"
    assert _check(needs).returncode == 0


def test_all_successful_checks_pass():
    assert _check(_needs()).returncode == 0


def test_success_gate_depends_on_every_other_job():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    assert set(jobs["ci-success"]["needs"]) == set(jobs) - {"ci-success"}


@pytest.mark.parametrize("missing", [None, "src/main.py", "plugins/example/manifest.json"])
def test_structure_step_still_detects_missing_files(tmp_path, missing):
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    step = next(s for s in jobs["detect-changes"]["steps"] if s.get("id") == "structure")
    for filename in (
        "src/__init__.py",
        "src/main.py",
        "src/config.py",
        "plugins/example/__init__.py",
        "plugins/example/manifest.json",
    ):
        if filename != missing:
            path = tmp_path / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]], cwd=tmp_path, capture_output=True, timeout=5
    )
    assert (result.returncode == 0) == (missing is None)


def test_preflight_gate_receives_raw_failures_not_continue_on_error_conclusions():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    outputs = jobs["detect-changes"]["outputs"]
    assert outputs["image_formats_result"] == "${{ steps.image_formats.outcome }}"
    assert outputs["structure_result"] == "${{ steps.structure.outcome }}"
    image_check = next(s for s in jobs["detect-changes"]["steps"] if s.get("id") == "image_formats")
    assert "if" not in image_check
