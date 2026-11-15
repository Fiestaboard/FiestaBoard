"""Historical update scenarios must survive a release's package-version bump.

Run in a fresh interpreter so every consumer imports the v11 package version,
just as on the Version PR. Scenario fixtures may pin their own stable/beta
version; the v11 release suite must still enforce the isolated Alpha lane.
"""

import os
import subprocess
import sys
from pathlib import Path

SCENARIO_SUITES = (
    "test_beta_graduates_to_stable",
    "test_beta_update_stays_on_beta",
    "test_channel_aware_discovery",
    "test_channel_survives_reboot",
    "test_mcp_state_effects_settings",
    "test_release_channel",
    "test_system_contract",
    "test_system_endpoints",
    "test_stale_sidecar_is_visible",
    "test_leaving_the_beta",
    "test_response_shape_goldens",
    "test_v11_release",
)


def test_update_scenarios_with_a_v11_package_version():
    root = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items() if key not in {"VERSION", "PYTEST_ADDOPTS"}}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import src; src.__version__ = '11.0.0-alpha.0'; import pytest, sys; sys.exit(pytest.main(sys.argv[1:]))",
            "-q",
            "--tb=short",
            *(f"tests/{name}.py" for name in SCENARIO_SUITES),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
