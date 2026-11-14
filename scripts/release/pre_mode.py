"""Keep Changesets pre mode on the branch it belongs to.

``.changeset/pre.json`` is a committed file, so git carries it wherever a merge
goes. Two mistakes publish the wrong thing:

- pre.json in pre mode reaching ``main``: main starts cutting ``-beta.N``
  prereleases instead of stable releases.
- ``alpha`` leaving pre mode: the Release workflow opens a STABLE Version PR
  against alpha and ships it, moving ``:latest`` from the wrong branch.

``check_pre_mode_for_base`` blocks the first at PR time (ci.yml's
release-guards job); ``alpha_release_action`` stops the second at release time
(release.yml).

Standard library only, so CI runs it with bare ``python3``::

    python3 scripts/release/pre_mode.py check-base <base-ref>
    python3 scripts/release/pre_mode.py alpha-action   # prints action=release|skip
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PRE_JSON = Path(".changeset/pre.json")
ALPHA_BRANCH = "alpha"
#: The prerelease identifier: alpha publishes ``X.Y.Z-beta.N``. It matches the
#: app's "beta" update channel and continues the old ``vX.Y.Z-beta.N`` tags.
PRE_TAG = "beta"


@dataclass(frozen=True)
class PreJson:
    """The two fields of pre.json this module reads."""

    mode: str
    tag: str


@dataclass(frozen=True)
class Result:
    ok: bool
    reason: str  # always one line


def _describe(pre: PreJson | None) -> str:
    if pre is None:
        return "there is no pre.json"
    return f'pre.json has mode "{pre.mode}", tag "{pre.tag}"'


def check_pre_mode_for_base(base_ref: str, pre: PreJson | None) -> Result:
    """Whether a PR's resulting pre.json is legal for the branch it targets."""
    if base_ref == "main":
        # Exit mode is the promotion PR from alpha: main's next Version PR
        # computes the stable version and deletes pre.json.
        if pre is not None and pre.mode != "exit":
            return Result(
                False,
                f"main must not be in prerelease mode, but {_describe(pre)}. "
                'Run "npx changeset pre exit" on alpha before promoting it.',
            )
        return Result(True, f"main: {_describe(pre)} — ok.")

    if base_ref == "v11":
        if pre is None or pre.tag != "alpha" or pre.mode not in ("pre", "exit"):
            return Result(
                False,
                f'v11 must stay in "alpha" prerelease mode, but {_describe(pre)}. Run "npx changeset pre enter alpha".',
            )
        return Result(True, f"v11: {_describe(pre)} — ok.")

    if base_ref == ALPHA_BRANCH:
        if pre is None or pre.tag != PRE_TAG:
            return Result(
                False,
                f'alpha must stay in "{PRE_TAG}" prerelease mode, but {_describe(pre)}. '
                f'Run "npx changeset pre enter {PRE_TAG}".',
            )
        return Result(True, f"alpha: {_describe(pre)} — ok.")

    return Result(True, f"{base_ref} is not a release branch — pre mode unchecked.")


def alpha_release_action(pre: PreJson | None) -> Literal["release", "skip"]:
    """What release.yml may do on ``alpha``.

    ``skip`` while a promotion is in progress (exit mode). Raises when alpha
    is not in beta pre mode at all.
    """
    if pre is None or pre.tag != PRE_TAG:
        raise ValueError(
            f"Refusing to release from alpha: {_describe(pre)}. alpha releases only in "
            f'"{PRE_TAG}" prerelease mode — run "npx changeset pre enter {PRE_TAG}".'
        )
    return "skip" if pre.mode == "exit" else "release"


def read_pre_json(path: Path = PRE_JSON) -> PreJson | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return PreJson(mode=data["mode"], tag=data["tag"])


def main(argv: list[str]) -> int:
    command = argv[0] if argv else ""
    try:
        if command == "check-base" and len(argv) == 2:
            result = check_pre_mode_for_base(argv[1], read_pre_json())
            print(f"reason={result.reason}")
            if not result.ok:
                print(f"::error title=Prerelease mode::{result.reason}", file=sys.stderr)
                return 1
            print(result.reason, file=sys.stderr)
            return 0
        if command == "v11-action" and len(argv) == 1:
            pre = read_pre_json()
            result = check_pre_mode_for_base("v11", pre)
            if not result.ok:
                raise ValueError(result.reason)
            print(f"action={'skip' if pre.mode == 'exit' else 'release'}")
            print(result.reason, file=sys.stderr)
            return 0
        if command == "alpha-action" and len(argv) == 1:
            action = alpha_release_action(read_pre_json())
            print(f"action={action}")
            print(
                "alpha is exiting prerelease mode (promotion in progress) — not versioning or releasing here."
                if action == "skip"
                else f"alpha is in {PRE_TAG} prerelease mode — releasing.",
                file=sys.stderr,
            )
            return 0
    except ValueError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    print(
        "usage: pre_mode.py check-base <base-ref> | pre_mode.py alpha-action | pre_mode.py v11-action", file=sys.stderr
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
