"""Integration failures must retain the screenshots/traces Playwright writes."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_integration_upload_collects_playwright_failure_artifacts(tmp_path):
    workflow = yaml.safe_load((ROOT / ".github/workflows/integration-tests.yml").read_text())
    steps = workflow["jobs"]["integration-tests"]["steps"]
    upload = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact"))
    # Read the runner's configured default rather than duplicating it here.
    config = (ROOT / "web/playwright.config.ts").read_text()
    output_dir = re.search(r'outputDir:\s*process\.env\.PLAYWRIGHT_OUTPUT_DIR\s*\|\|\s*"([^"]+)"', config)
    assert output_dir, "Update this contract check if Playwright's output configuration changes"
    artifacts = tmp_path / "web" / output_dir.group(1) / "failed-test-retry1"
    artifacts.mkdir(parents=True)
    trace = artifacts / "trace.zip"
    screenshot = artifacts / "test-failed-1.png"
    trace.touch()
    screenshot.touch()

    collected = set()
    for pattern in upload["with"]["path"].splitlines():
        for match in tmp_path.glob(pattern.strip().rstrip("/")):
            collected.update(match.rglob("*") if match.is_dir() else [match])
    assert {trace, screenshot} <= collected, "Integration upload misses Playwright's failure artifacts"
    assert upload["if"] == "${{ !cancelled() }}", "Failed tests must still upload evidence"
