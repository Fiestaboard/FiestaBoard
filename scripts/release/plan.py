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


def _core(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split("-", 1)[0].split(".")
    return int(major), int(minor), int(patch)


def plan_release(*, branch: str, version: str, release_exists: bool, newest_stable: str | None = None) -> Plan:
    """Pure decision. Raises ValueError when the branch would ship the wrong kind of version.

    ``newest_stable`` is the highest released stable version. Whatever this
    releases must sort above it. For a prerelease that is the whole point:
    beta installs take the newest version across both channels
    (update_service._latest_for_channel), so a ``10.3.3-beta.1`` cut after
    ``10.3.3`` shipped is invisible to them and walks them back onto stable
    (#1992). Changesets bumps pre mode from the version alpha was created at,
    so this happens whenever main releases past alpha's target mid-cycle;
    the fix is to restart alpha (RELEASING.md).
    """
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

    if newest_stable is not None and _core(version) <= _core(newest_stable):
        raise ValueError(
            f"{version} would not sort above the newest stable release {newest_stable}. "
            + (
                "Restart alpha from main (docs/internal/development/RELEASING.md, Lifecycle)."
                if prerelease
                else "main's version went backwards — check package.json and the Version PR."
            )
        )

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


def newest_stable_release() -> str | None:
    """The highest stable version among published GitHub Releases."""
    result = _run(
        "gh", "release", "list", "--exclude-drafts", "--exclude-pre-releases",
        "--limit", "100", "--json", "tagName", "--jq", ".[].tagName",
    )  # fmt: skip
    if result.returncode != 0:
        raise RuntimeError(f"gh release list failed: {result.stderr.strip()}")
    stable = [tag[1:] for tag in result.stdout.split() if re.fullmatch(r"v\d+\.\d+\.\d+", tag)]
    return max(stable, key=_core) if stable else None


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
        exists = release_exists(f"v{version}")
        plan = plan_release(
            branch=argv[0],
            version=version,
            release_exists=exists,
            newest_stable=None if exists else newest_stable_release(),
        )
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
