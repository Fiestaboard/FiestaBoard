"""Decide whether a PR must carry a changeset.

Under Changesets nothing releases until a changeset says so. A change to the
app that merges without one is not lost (the next release's image is built
from the whole tree), but it reaches users only when some unrelated change
happens to release, and it is missing from that release's changelog. This
check turns that silent miss into a red PR.

"Shipped" means it changes what users install: the Docker image (everything
the Dockerfile copies in) or the FiestaPi image (``pi-image/``). The list is
an allowlist that mirrors the Dockerfile's ``COPY`` sources, and
``tests/test_changeset_check.py`` parses the Dockerfile so a new ``COPY`` can't
quietly escape it.

Deliberately NOT shipped:

- ``fiestaupdater/``: the updater sidecar is its own image on its own cadence
  (build-fiestaupdater.yml). PR #1969 changed only the sidecar and cut 8.36.0,
  an app image byte-identical to 8.35.5 that every install was then prompted
  to take.
- ``tests/``: copied into the image, but changing them changes no behaviour.
- Markdown, docs, CI, compose files, and repo tooling.

Standard library only, so CI runs it with bare ``python3``::

    python3 scripts/release/changeset_check.py <base-sha> <head-sha>
    (reads HEAD_REF and PR_LABELS — comma-separated — from the environment)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase

#: The label that waives the check, for changes that genuinely release nothing.
SKIP_LABEL = "no-changeset"

#: Head refs that never need a changeset of their own.
#:
#: - ``changeset-release/*`` is the Version PR: it consumes changesets, so it
#:   would otherwise fail its own check.
#: - ``main`` is a main→alpha sync: main's changesets were consumed by main's
#:   own release before the sync, so the shipped diff arrives with none.
#: - ``alpha`` is the promotion PR into main: alpha's changesets were consumed
#:   by its beta releases (Changesets v3 keeps them in ``.changeset/pre/``),
#:   and main's next Version PR turns them into the stable changelog.
#: - ``dependabot/*``: dependency bumps ride along with the next release (the
#:   image is built from the whole tree). Add a changeset to a Dependabot PR by
#:   hand when it should release on its own, such as a security fix.
EXEMPT_HEAD_REFS = (
    re.compile(r"^changeset-release/"),
    re.compile(r"^main$"),
    re.compile(r"^alpha$"),
    re.compile(r"^dependabot/"),
)

#: Paths whose change reaches users through a release. Keep in step with the
#: Dockerfile's COPY lines (a test enforces it).
SHIPPED_PATTERNS = (
    "Dockerfile",
    ".dockerignore",
    "requirements.txt",
    "web/*",
    "src/*",
    "plugins/*",
    "staff-picks/*",
    "plugin-registry.json",
    "plugin-previews.json",
    "outputs.lock.json",
    "scripts/seed_outputs.py",
    "nginx.conf",
    "starting.html",
    "supervisord.conf",
    "supervisord-dev.conf",
    "entrypoint.sh",
    # The FiestaPi image is rebuilt for every stable release.
    "pi-image/*",
)

#: Inside a shipped path, still not a reason to release.
NOT_SHIPPED_PATTERNS = (
    "*.md",
    "*.mdx",
    "tests/*",
    "*/tests/*",
    # Playwright specs; .dockerignore keeps them out of the image.
    "*.spec.ts",
    "*.spec.tsx",
    "*/__tests__/*",
    "*.test.ts",
    "*.test.tsx",
    "*.stories.tsx",
)

MAX_LISTED = 5


@dataclass(frozen=True)
class Result:
    ok: bool
    reason: str  # always one line


def _matches(path: str, patterns: Iterable[str]) -> bool:
    # fnmatch's `*` crosses `/`, so "web/*" covers the whole subtree.
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def is_changeset_file(path: str) -> bool:
    """A top-level ``.changeset/<name>.md``, but not the README.

    ``.changeset/pre/`` (where Changesets v3 keeps consumed prerelease
    changesets) is excluded by the single-segment match.
    """
    return re.fullmatch(r"\.changeset/[^/]+\.md", path) is not None and path != ".changeset/README.md"


def is_shipped(path: str) -> bool:
    return _matches(path, SHIPPED_PATTERNS) and not _matches(path, NOT_SHIPPED_PATTERNS)


def check_changeset(*, files: list[str], added_files: list[str], head_ref: str, labels: list[str]) -> Result:
    """``files``: every path the PR changes; ``added_files``: paths it adds."""
    if any(pattern.search(head_ref) for pattern in EXEMPT_HEAD_REFS):
        return Result(True, f"Head ref {head_ref} is exempt from the changeset check.")
    if SKIP_LABEL in labels:
        return Result(True, f"The {SKIP_LABEL} label waives the changeset check.")

    changesets = [p for p in added_files if is_changeset_file(p)]
    if changesets:
        return Result(True, f"Changeset found: {', '.join(changesets)}.")

    shipped = [p for p in files if is_shipped(p)]
    if not shipped:
        return Result(True, "Nothing that ships changed — no changeset needed.")

    listed = ", ".join(shipped[:MAX_LISTED])
    more = f" and {len(shipped) - MAX_LISTED} more" if len(shipped) > MAX_LISTED else ""
    return Result(
        False,
        f"This PR changes shipped code ({listed}{more}) but adds no changeset. "
        'Run "npx changeset" and commit the file it writes, or "npx changeset --empty" '
        f"(or add the {SKIP_LABEL} label) if this should not release.",
    )


def _git_lines(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: changeset_check.py <base-sha> <head-sha>", file=sys.stderr)
        return 2
    # Three-dot: what the PR introduces relative to where it branched, not
    # what the base has gained since.
    rng = f"{argv[0]}...{argv[1]}"
    result = check_changeset(
        files=_git_lines("diff", "--name-only", rng),
        added_files=_git_lines("diff", "--name-only", "--diff-filter=A", rng),
        head_ref=os.environ.get("HEAD_REF", ""),
        labels=[label.strip() for label in os.environ.get("PR_LABELS", "").split(",") if label.strip()],
    )
    print(f"ok={str(result.ok).lower()}")
    print(f"reason={result.reason}")
    if not result.ok:
        print(f"::error title=Missing changeset::{result.reason}", file=sys.stderr)
        return 1
    print(result.reason, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
