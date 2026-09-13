"""A release must mean the app actually changed (#1955 follow-on).

`release.yml` fires on every push to `main` whose changed files are not all
in `paths-ignore`, bumps the version, builds the app image and creates a
GitHub release that every install is then prompted to take.

The updater sidecar does not belong in that set. It ships as its own image
from its own workflow (`build-fiestaupdater.yml`, keyed on the same paths)
and is not versioned with the app, so a sidecar-only change produces an app
image whose code is byte-identical to the previous one.

That is exactly what happened: PR #1969 changed only `handler.sh` and its
bats tests, and cut 8.36.0. The entire diff against 8.35.5, outside version
strings, was the sidecar — and every FiestaBoard prompted its owner to
install it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
RELEASE = WORKFLOWS / "release.yml"
SIDECAR = WORKFLOWS / "build-fiestaupdater.yml"


def _triggers(path: Path) -> dict:
    # PyYAML reads the `on:` key as boolean True (YAML 1.1 truthiness).
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc.get(True, doc.get("on", {}))


def test_a_sidecar_only_change_does_not_cut_an_app_release():
    ignored = _triggers(RELEASE)["push"].get("paths-ignore", [])
    assert "fiestaupdater/**" in ignored, (
        "release.yml would cut an app release for a sidecar-only change. The "
        "resulting image is byte-identical to the previous one and every "
        "install is prompted to take it — see 8.36.0, whose whole diff "
        "outside version strings was fiestaupdater/."
    )


def test_the_sidecar_still_publishes_itself():
    """Ignoring it in release.yml is only safe because it has its own lane."""
    watched = _triggers(SIDECAR)["push"].get("paths", [])
    assert any("fiestaupdater" in p for p in watched), (
        "build-fiestaupdater.yml no longer builds on sidecar changes, so "
        "excluding them from release.yml would leave them unpublished."
    )
