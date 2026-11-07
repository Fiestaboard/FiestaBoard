"""Decide whether this push releases, and what.

The Release workflow runs changesets/action for the Version PR only (no
publish script). Whether to release is decided here, from one fact:
**the version in package.json has no GitHub Release yet**. Only merging the
Version PR changes that version, so many merges share one release, and
re-running after a failed build simply resumes it.

The image is built from ``release_sha``: the last first-parent commit that
changed package.json's version — the Version PR's merge — not whatever the
branch tip is by the time this runs. Otherwise a retry after a failed build
would label newer, unreviewed code with the old version.

Standard library only (plus ``git`` and ``gh`` on PATH)::

    python3 scripts/release/plan.py <branch>   # prints key=value lines for $GITHUB_OUTPUT
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: X.Y.Z, optionally -<id>.<n>; the shapes the update checker accepts.
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z]+(\.[0-9A-Za-z]+)*)?$")
STABLE_BRANCH = "main"
PRERELEASE_BRANCH = "alpha"
PRE_TAG = "beta"


@dataclass(frozen=True)
class Plan:
    release: bool
    version: str
    prerelease: bool
    reason: str

    @property
    def tag(self) -> str:
        return f"v{self.version}"


def plan_release(*, branch: str, version: str, release_exists: bool) -> Plan:
    """Pure decision. Raises ValueError when the branch would ship the wrong kind of version."""
    if not VERSION_RE.match(version):
        raise ValueError(f"package.json version {version!r} is not X.Y.Z or X.Y.Z-{PRE_TAG}.N")
    prerelease = "-" in version

    if release_exists:
        return Plan(False, version, prerelease, f"v{version} is already released — nothing to do.")

    if branch == STABLE_BRANCH and prerelease:
        raise ValueError(
            f"main would release prerelease {version}. main must never be in pre mode — check .changeset/pre.json."
        )
    if branch == PRERELEASE_BRANCH and not re.search(rf"-{PRE_TAG}\.\d+$", version):
        raise ValueError(
            f"alpha would release {version}, which is not a -{PRE_TAG}.N prerelease. "
            f'alpha releases only in "{PRE_TAG}" pre mode.'
        )
    if branch not in (STABLE_BRANCH, PRERELEASE_BRANCH):
        raise ValueError(f"{branch} is not a release branch.")

    kind = "prerelease" if prerelease else "stable release"
    return Plan(True, version, prerelease, f"v{version} has no GitHub Release — cutting the {kind}.")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), capture_output=True, text=True)


def release_exists(tag: str) -> bool:
    result = _run("gh", "release", "view", tag, "--json", "tagName")
    if result.returncode == 0:
        return True
    if "release not found" in result.stderr.lower():
        return False
    raise RuntimeError(f"gh release view {tag} failed: {result.stderr.strip()}")


def version_commit() -> str:
    """The last first-parent commit that changed package.json's version line."""
    result = _run("git", "log", "--first-parent", "-1", "--format=%H", "-G", '"version":', "--", "package.json")
    sha = result.stdout.strip()
    if result.returncode != 0 or not sha:
        raise RuntimeError(f"could not find the commit that set package.json's version: {result.stderr.strip()}")
    return sha


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: plan.py <branch>", file=sys.stderr)
        return 2
    version = json.loads(Path("package.json").read_text(encoding="utf-8"))["version"]
    try:
        plan = plan_release(branch=argv[0], version=version, release_exists=release_exists(f"v{version}"))
        sha = version_commit() if plan.release else ""
    except (ValueError, RuntimeError) as error:
        print(f"::error title=Release plan::{error}", file=sys.stderr)
        return 1
    print(f"release={str(plan.release).lower()}")
    print(f"version={plan.version}")
    print(f"tag={plan.tag}")
    print(f"prerelease={str(plan.prerelease).lower()}")
    print(f"release_sha={sha}")
    print(f"reason={plan.reason}")
    print(plan.reason, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
