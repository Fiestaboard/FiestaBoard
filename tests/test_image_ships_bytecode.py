"""The image must ship precompiled bytecode (issue #1955).

``.dockerignore`` excludes ``__pycache__/``, so nothing the build copies in
carries bytecode. Without an explicit ``compileall`` the first import in a
fresh container — the one uvicorn performs at boot — compiles every module
under ``src/`` and ``plugins/`` before the API answers anything.

Measured as first-import-in-a-fresh-container — the scenario that actually
recurs — alternating conditions over 5 rounds so the host page cache cannot
favour either: **484.2 ms with the cache vs 565.1 ms without** (variance
under 7 ms either way), so **~81 ms (14%)** paid again on every container
start and every reboot, and more on a Pi.

This pins the RELATIONSHIP, not a line number: as long as ``__pycache__``
is excluded from the build context, the Dockerfile has to compile the
sources it copies. Deleting either half alone fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Source trees copied into the runtime image that uvicorn imports at boot.
COMPILED_TREES = ("src", "plugins")


def _dockerignore_excludes_pycache() -> bool:
    text = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    return any(line.strip().rstrip("/") == "__pycache__" for line in text.splitlines())


def _compileall_targets() -> set[str]:
    """Every path named by a ``compileall`` invocation in the Dockerfile."""
    text = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    targets: set[str] = set()
    for match in re.finditer(r"compileall\b([^\n]*)", text):
        for token in match.group(1).split():
            if token.startswith("-") or token in {"||", "true", "&&"}:
                continue
            targets.add(token.rstrip("/").rsplit("/", 1)[-1])
    return targets


def test_the_dockerfile_precompiles_every_source_tree_it_copies():
    assert _dockerignore_excludes_pycache(), (
        "`.dockerignore` no longer excludes __pycache__. If bytecode is now "
        "copied in from the build context, this guard is obsolete — but it is "
        "also now shipping the host's bytecode, which is worse. Decide which."
    )

    targets = _compileall_targets()
    missing = [tree for tree in COMPILED_TREES if tree not in targets]
    assert not missing, (
        f"the Dockerfile copies {missing} into the image but never compiles "
        f"them, so every container start pays the compile again "
        f"(measured ~81ms on arm64, more on a Pi). compileall targets "
        f"found: {sorted(targets) or 'none'}"
    )
