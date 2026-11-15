"""Keep Version PR release-gate PWA coverage on real secure/insecure origins."""

from pathlib import Path

import yaml


def _steps():
    path = Path(__file__).resolve().parents[1] / ".github/workflows/integration-tests.yml"
    return yaml.safe_load(path.read_text())["jobs"]["integration-tests"]["steps"]


def _step(name):
    return next(step for step in _steps() if step.get("name") == name)


def test_full_suite_workers_have_distinct_loopback_origins():
    start = _step("Start 4 mock board + mock cloud + FiestaBoard containers (full suite)")["run"]
    assert '-p "127.0.0.1:$((4420 + i)):3000"' in start
    assert 'WORKER_URLS="${WORKER_URLS}http://localhost:$((4420 + i))"' in start
    assert 'PWA_HTTP_BASE_URL="http://$FB_IP:3000"' in start
    assert 'echo "PWA_HTTP_MOCK_URL=http://$MOCK_IP:7000" >> $GITHUB_ENV' in start
    assert 'echo "PWA_HTTP_MOCK_HOST=$MOCK_IP" >> $GITHUB_ENV' in start


def test_plain_http_cases_run_separately_even_after_secure_suite_failure():
    full = _step("Run integration tests (full suite on the Version PR)")
    assert "--grep-invert=plain.http:" in full["run"]
    plain = _step("Run insecure HTTP PWA tests (full suite)")
    assert "!cancelled()" in plain["if"]
    assert "startsWith(github.head_ref, 'changeset-release/')" in plain["if"]
    assert "steps.containers_ready.outcome == 'success'" in plain["if"]
    assert "pwa-https.spec.ts --workers=1" in plain["run"]
    assert plain["env"]["BASE_URL"] == "${{ env.PWA_HTTP_BASE_URL }}"
    assert plain["env"]["WORKER_URLS"] == ""
    assert plain["env"]["MOCK_BOARD_URL"] == "${{ env.PWA_HTTP_MOCK_URL }}"
    assert plain["env"]["MOCK_BOARD_HOST"] == "${{ env.PWA_HTTP_MOCK_HOST }}"
    assert plain["env"]["PLAYWRIGHT_OUTPUT_DIR"] != "playwright-test-results"
    artifacts = _step("Upload test results")["with"]["path"]
    assert plain["env"]["PLAYWRIGHT_OUTPUT_DIR"] in artifacts
    assert plain["env"]["PLAYWRIGHT_JSON_OUTPUT_FILE"] in artifacts
