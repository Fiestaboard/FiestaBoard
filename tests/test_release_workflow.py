"""The shape of the Changesets release workflow (.github/workflows/release.yml).

Each assertion pins a decision whose failure is silent or expensive; see the
comments in release.yml and docs/internal/development/RELEASING.md.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
RELEASE = WORKFLOWS / "release.yml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    # PyYAML reads the `on:` key as boolean True (YAML 1.1 truthiness).
    return doc.get(True, doc.get("on", {}))


def _steps(job: dict) -> list[dict]:
    return job.get("steps", [])


def _step(job: dict, uses_prefix: str) -> dict:
    matches = [s for s in _steps(job) if str(s.get("uses", "")).startswith(uses_prefix)]
    assert len(matches) == 1, f"expected one {uses_prefix} step, found {len(matches)}"
    return matches[0]


DOC = _load(RELEASE)
JOBS = DOC["jobs"]


def test_runs_on_push_to_both_release_branches_without_path_filters():
    """push, not workflow_run (GITHUB_REF would be main for an alpha run); no
    paths-ignore, so a changeset-only push still updates the Version PR."""
    on = _triggers(DOC)
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"]["branches"] == ["main", "alpha"]
    assert "paths-ignore" not in on["push"] and "paths" not in on["push"]


def test_only_release_branches_of_the_real_repo_run():
    condition = JOBS["version"]["if"]
    assert "github.repository == 'Fiestaboard/FiestaBoard'" in condition
    assert "github.ref_name == 'main'" in condition and "github.ref_name == 'alpha'" in condition


def test_concurrency_is_per_branch_and_never_cancels():
    assert DOC["concurrency"]["group"] == "release-${{ github.ref_name }}"
    assert DOC["concurrency"]["cancel-in-progress"] is False


def test_the_action_only_maintains_the_version_pr():
    step = _step(JOBS["version"], "changesets/action@")
    assert step["uses"] == "changesets/action@v2"
    with_ = step["with"]
    assert with_["github-token"] == "${{ steps.app-token.outputs.token }}"
    assert with_["version-script"] == "npm run version-packages"
    # No publish script: plan.py decides releases, so a retry can resume one.
    assert "publish-script" not in with_
    # v2 throws when a GITHUB_TOKEN env differs from the github-token input.
    assert "GITHUB_TOKEN" not in step.get("env", {})


def test_version_prs_are_opened_with_the_app_token():
    """A PR opened with GITHUB_TOKEN has its CI gated in action_required."""
    mint = _step(JOBS["version"], "actions/create-github-app-token@")
    assert mint["with"]["app-id"] == "${{ secrets.CLAUDE_BOT_APP_ID }}"


def test_alpha_is_guarded_by_pre_mode():
    steps = {s.get("id"): s for s in _steps(JOBS["version"])}
    assert "pre_mode.py alpha-action" in steps["alpha"]["run"]
    action = _step(JOBS["version"], "changesets/action@")
    assert "steps.alpha.outputs.action == 'release'" in action["if"]
    assert "steps.alpha.outputs.action == 'release'" in steps["plan"]["if"]


def test_everything_downstream_is_gated_on_the_plan():
    assert JOBS["build"]["if"] == "needs.version.outputs.release == 'true'"
    for job in ("merge", "release", "dockerhub-description"):
        assert "version" in JOBS[job]["needs"]


def test_the_image_is_built_from_the_version_commit():
    checkout = _step(JOBS["build"], "actions/checkout@")
    assert checkout["with"]["ref"] == "${{ needs.version.outputs.release_sha }}"
    build = _step(JOBS["build"], "docker/build-push-action@")
    assert build["with"]["target"] == "runtime"  # issue #1377


def test_latest_moves_only_for_stable_releases():
    run = next(s["run"] for s in _steps(JOBS["merge"]) if s.get("name") == "Create manifest list and push")
    assert 'if [ "$PRERELEASE" = "true" ]; then MOVING=beta; else MOVING=latest; fi' in run


def test_the_release_comes_after_the_image():
    """Installs discover updates from releases: never point one at an unpullable image."""
    assert set(JOBS["release"]["needs"]) == {"version", "merge"}


def test_stable_only_side_effects():
    steps = {s.get("name"): s for s in _steps(JOBS["release"])}
    for name in (
        "Generate AI summary with Claude",
        "Notify docs site repo of release",
        "Build the FiestaPi image for this release",
    ):
        assert steps[name]["if"] == "needs.version.outputs.prerelease != 'true'", name
    assert JOBS["dockerhub-description"]["if"] == "needs.version.outputs.prerelease != 'true'"


def test_prereleases_stay_off_releases_latest():
    script = next(s["with"]["script"] for s in _steps(JOBS["release"]) if s.get("name") == "Render and publish release")
    assert "prerelease," in script
    assert "make_latest: prerelease ? 'false' : 'true'" in script


def test_the_pi_image_is_dispatched_not_chained():
    """build-fiestapi.yml must not fire on every release-workflow run."""
    pi = _load(WORKFLOWS / "build-fiestapi.yml")
    on = _triggers(pi)
    assert "workflow_run" not in on
    assert "release_tag" in on["workflow_dispatch"]["inputs"]


def test_no_old_release_rigging_remains():
    text = RELEASE.read_text(encoding="utf-8")
    for gone in (
        "version-sync.js patch",
        "bump version to",
        "revert-on-failure",
        "RELEASE_PAT || secrets.GITHUB_TOKEN",
    ):
        assert gone not in text, gone
    assert not (WORKFLOWS / "release-beta.yml").exists()
