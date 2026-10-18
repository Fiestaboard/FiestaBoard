"""Execute the composite action's shell steps against controlled installers.

A missing/failed npm install must never fall through to an unpinned npx
fetch or a successful browser setup. No network or browsers are needed.
"""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / ".github/actions/setup-web-e2e/action.yml"


@pytest.mark.parametrize("npm_status,browser_status", [(0, 0), (17, 0), (0, 23)])
def test_browser_setup_requires_successful_locked_install(tmp_path, npm_status, browser_status):
    web = tmp_path / "web"
    web.mkdir()
    (web / "package-lock.json").write_text("{}")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text(
        "#!/bin/bash\nset -eu\n"
        '[ "$1" = ci ] || exit 90\n'
        "sleep 0.1\n"
        f"exit_code={npm_status}\n"
        '[ "$exit_code" = 0 ] || exit "$exit_code"\n'
        'touch "$TEST_ROOT/installed"\n'
    )
    npx = bin_dir / "npx"
    npx.write_text(
        "#!/bin/bash\nset -eu\n"
        '[ -f "$TEST_ROOT/installed" ] || exit 91\n'
        '[ "$1" = --no-install ] || exit 92\n'
        'echo "$*" >> "$TEST_ROOT/browser-calls"\n'
        f"exit {browser_status}\n"
    )
    npm.chmod(0o755)
    npx.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "TEST_ROOT": str(tmp_path)}
    action = yaml.safe_load(ACTION.read_text())
    result = None
    for step in action["runs"]["steps"]:
        if "run" not in step:
            continue
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
            cwd=tmp_path / step.get("working-directory", "."),
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode:
            break
    assert result is not None
    assert result.returncode == (npm_status or browser_status), result.stderr
    calls = tmp_path / "browser-calls"
    if npm_status:
        assert not calls.exists()
    elif not browser_status:
        assert "--with-deps chromium" in calls.read_text()
