"""Keep known developer-tool fixes in reproducible installs on this branch.

These are lockfile regressions, not evidence of a running vulnerable service.
Storybook: GHSA-f2ph-cmg5-wxc8 / GHSA-px85-f4q5-jh77 (10.6.2 fixes).
markdown-it: 15.0.3 fixes quadratic parsing of references and inline HTML.
follow-redirects: GHSA-8r9p-f939-6h3c (1.16.1 fixes sensitiveHeaders escaping).
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("lockfile", "package", "minimum"),
    [
        ("web/package-lock.json", "storybook", (10, 6, 2)),
        ("package-lock.json", "markdown-it", (15, 0, 3)),
        ("web/package-lock.json", "follow-redirects", (1, 16, 1)),
    ],
)
def test_locked_developer_tool_includes_known_security_fixes(lockfile, package, minimum):
    packages = json.loads((ROOT / lockfile).read_text())["packages"]
    resolved = {path: entry["version"] for path, entry in packages.items() if path.endswith(f"node_modules/{package}")}
    assert resolved, f"{package} is missing from {lockfile}; review this guard if the tool was removed"
    for path, version in resolved.items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"Review prerelease security coverage: {path}@{version}"
        assert tuple(map(int, version.split("."))) >= minimum, (
            f"{lockfile}: {path}@{version} lacks the known fixes in {'.'.join(map(str, minimum))}+"
        )
