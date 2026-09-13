"""The beta channel must not be able to masquerade as stable (#1955 follow-on).

`release-beta.yml` publishes from `next` on every merge. Four of its
properties are what keep a beta from reaching someone who never asked for
one, and every single one is a one-line edit away from silently inverting:

* it must never push `:latest` — that tag *is* the stable channel, and the
  Pi image and `docker-compose.hub.yml` both follow it unconditionally;
* its GitHub release must be a **prerelease**, because `/releases/latest`
  (what stable installs poll, `update_service.py:143-159`) is defined as
  excluding prereleases. That exclusion is the entire reason a stable user
  cannot be offered a beta;
* its workflow `name:` must differ from the stable one, because
  `build-fiestapi.yml` keys a `workflow_run` trigger on the literal string
  "Release: Publish Image" — matching it would fire a 60-minute Pi build on
  every beta;
* it must never commit a version bump, because `scripts/version-sync.js`
  rejects any non-`X.Y.Z` string, so a committed `-beta.N` would break the
  next *stable* release.

These are asserted against the workflow files rather than a live run,
because a live run publishes to Docker Hub — there is no safe way to find
out empirically that the guard broke.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
BETA = WORKFLOWS / "release-beta.yml"
STABLE = WORKFLOWS / "release.yml"
PI = WORKFLOWS / "build-fiestapi.yml"


def _load(path: Path) -> dict:
    # PyYAML parses the `on:` key as the boolean True (YAML 1.1 truthiness).
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    return doc.get(True, doc.get("on", {}))


@pytest.fixture(scope="module")
def beta_text() -> str:
    return BETA.read_text(encoding="utf-8")


def test_the_beta_workflow_never_pushes_the_latest_tag(beta_text):
    """`:latest` is the stable channel. The Pi image follows it unconditionally."""
    offenders = [
        line.strip()
        for line in beta_text.splitlines()
        if "fiestaboard/fiestaboard:latest" in line and not line.strip().startswith("#")
    ]
    assert not offenders, (
        "release-beta.yml references the stable `:latest` tag outside a comment: "
        f"{offenders}. Every Pi and every default docker-compose install follows "
        "that tag, so publishing a beta to it ships the beta to everyone."
    )


def test_the_beta_release_is_marked_prerelease(beta_text):
    """`/releases/latest` excludes prereleases — that is what protects stable users."""
    assert "prerelease: true" in beta_text, (
        "release-beta.yml must create its GitHub release with prerelease: true. "
        "Without it the beta becomes /releases/latest, which is the endpoint "
        "every stable install polls for updates."
    )
    assert "make_latest: 'false'" in beta_text or 'make_latest: "false"' in beta_text, (
        "release-beta.yml must set make_latest false so the stable release keeps "
        "the 'latest' pointer release.yml deliberately pins."
    )


def test_the_beta_workflow_name_cannot_trigger_the_pi_build():
    """`build-fiestapi.yml` keys a workflow_run trigger on the stable name."""
    beta_name = _load(BETA)["name"]
    stable_name = _load(STABLE)["name"]
    assert beta_name != stable_name, "beta and stable workflows share a name"

    pi_triggers = _triggers(_load(PI))
    watched = pi_triggers.get("workflow_run", {}).get("workflows", [])
    assert stable_name in watched, (
        "build-fiestapi.yml no longer watches the stable release workflow by name; "
        "this test's premise needs rechecking."
    )
    assert beta_name not in watched, (
        f"build-fiestapi.yml watches {beta_name!r}, so every beta would kick off the 60-minute Pi image build."
    )


def test_the_beta_workflow_only_publishes_from_next():
    triggers = _triggers(_load(BETA))
    assert triggers["push"]["branches"] == ["next"], (
        "release-beta.yml must publish only from `next`; it builds and pushes to Docker Hub with no review gate."
    )


def test_the_beta_workflow_never_commits_a_version_bump(beta_text):
    """`version-sync.js` throws on a non-X.Y.Z version, breaking stable releases."""
    # Comments are excluded: this file's own header *explains* why it must not
    # run version-sync.js, and a substring match would flag that prose.
    executable = [line for line in beta_text.splitlines() if not line.strip().startswith("#")]
    for forbidden in ("version-sync.js", "git commit", "git push"):
        offenders = [line.strip() for line in executable if forbidden in line]
        assert not offenders, (
            f"release-beta.yml runs {forbidden!r}: {offenders}. The beta version is "
            "a build-arg only — committing it would put a `-beta.N` string in "
            "package.json, which scripts/version-sync.js rejects on the next "
            "stable release."
        )


def test_the_beta_workflow_does_not_dispatch_to_the_docs_site(beta_text):
    """release.yml's dispatch snapshots fiestaboard.app to the released tag."""
    assert "fiestaboard.github.io" not in beta_text, (
        "release-beta.yml dispatches to the docs site, which would snapshot fiestaboard.app to a beta tag."
    )


def test_the_stable_workflow_does_not_publish_a_beta_tag():
    """The guard in the other direction: stable must not touch `:beta`."""
    stable_text = STABLE.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in stable_text.splitlines()
        if "fiestaboard/fiestaboard:beta" in line and not line.strip().startswith("#")
    ]
    assert not offenders, f"release.yml publishes to the beta tag: {offenders}"


def test_the_declared_beta_target_is_ahead_of_the_stable_version():
    """Betas must sort above the release they follow and below the one they precede.

    The target is declared in the workflow rather than derived, because
    deriving it gets it wrong in both available ways: the repo infers bump
    type from conventional-commit titles and no PR merged into `next` carries
    a major label (the breaking changes landed under plain `feat:`/`refactor:`
    titles), and deriving from package.json drifts the moment `main` ships —
    retroactively putting already-published betas *below* a real release.

    Declaring it moves the risk to one place, and this test plus the
    workflow's own runtime guard watch that place.
    """
    import json
    import re

    beta_text = BETA.read_text(encoding="utf-8")
    match = re.search(r'BETA_TARGET_VERSION:\s*"([^"]+)"', beta_text)
    assert match, "release-beta.yml no longer declares BETA_TARGET_VERSION"
    target = match.group(1)
    assert re.fullmatch(r"\d+\.\d+\.\d+", target), f"BETA_TARGET_VERSION {target!r} is not X.Y.Z"

    stable = json.loads((BETA.parent.parent.parent / "package.json").read_text())["version"]
    as_tuple = lambda v: tuple(int(p) for p in v.split("."))  # noqa: E731

    assert as_tuple(target) > as_tuple(stable), (
        f"betas target {target} but stable is already {stable}. Every beta published "
        f"from here would sort at or below a real release, and the update checker "
        f"would offer a 'newer' beta that is actually older. Raise "
        f"BETA_TARGET_VERSION in .github/workflows/release-beta.yml."
    )
