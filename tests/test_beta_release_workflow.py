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

import os
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


def _compute_beta_version(tags: list[str], tmp_path, *, override: str = "", registry_tags: tuple[str, ...] = ()):
    """Run the workflow's own beta-version script against a synthetic tag set.

    The script is extracted from `release-beta.yml` rather than reimplemented,
    so this exercises the shell that actually ships. It contains no Actions
    expressions; the Docker Hub listing reaches it through the
    `REGISTRY_BETA_TAGS` env var, which *registry_tags* stands in for.

    Returns `(returncode, version_or_None, combined_output)`.
    """
    import re
    import subprocess

    step = None
    for job in _load(BETA)["jobs"].values():
        for candidate in job.get("steps", []):
            if candidate.get("id") == "version":
                step = candidate
    assert step, "no step with id 'version' in release-beta.yml"
    script = step["run"]
    assert "${{" not in script, "unsubstituted Actions expression in the beta-version script"

    repo = tmp_path / "repo"
    repo.mkdir()
    env_git = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "base"], cwd=repo, check=True, env={**os.environ, **env_git}
    )
    for tag in tags:
        subprocess.run(["git", "tag", tag], cwd=repo, check=True)

    out_file = tmp_path / "gh_output"
    out_file.write_text("")
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=repo,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "BETA_TARGET_OVERRIDE": override,
            "REGISTRY_BETA_TAGS": "\n".join(registry_tags),
            "GITHUB_OUTPUT": str(out_file),
        },
    )
    written = out_file.read_text()
    match = re.search(r"^version=(.+)$", written, re.M)
    return proc.returncode, (match.group(1) if match else None), proc.stdout + proc.stderr


class TestBetaTargetDerivation:
    """Betas must sort above the release they follow and below the one they precede.

    The target used to be a hardcoded `BETA_TARGET_VERSION` in the workflow. It
    is now derived — newest stable tag, one minor ahead — so it cannot go stale
    between a release and someone remembering to raise it. That staleness was
    real: 9.0.0 shipped while the declared value still said 9.0.0, which made
    the workflow's own guard fail every push to `next`.

    Derived from TAGS rather than package.json on purpose. The objection that
    retired the previous attempt at deriving — "package.json drifts the moment
    `main` ships" — is correct, and applies to `next` in the other direction
    too: next's package.json lags `main` between a release and the next
    main -> next sync, so a minor bump off it would have targeted 8.39.0 while
    9.0.0-beta.43 already existed. Tags are the shipped truth.

    These run the workflow's real shell against synthetic tag sets, so they
    fail if the derivation's arithmetic or its tag filtering regresses — not
    merely if a literal disappears from the file.
    """

    def test_it_targets_one_minor_past_the_newest_stable_release(self, tmp_path):
        code, version, output = _compute_beta_version(["v8.39.0", "v9.0.0"], tmp_path)
        assert code == 0, output
        assert version == "9.1.0-beta.1"

    def test_prereleases_are_not_mistaken_for_the_release_to_aim_past(self, tmp_path):
        """A prerelease is not a shipped version, so it is not the base.

        The tag set is chosen so the two behaviours give different answers. With
        `9.0.0` + `9.0.0-beta.43` both paths land on 9.1.0 by coincidence, which
        would let a regression through; a prerelease of a *higher* minor
        separates them — off `9.0.0` the answer is 9.1.0, but counting
        `9.1.0-beta.5` as the base would say 9.2.0 and skip a release nobody
        shipped.
        """
        code, version, output = _compute_beta_version(["v9.0.0", "v9.1.0-beta.5"], tmp_path)
        assert code == 0, output
        assert version == "9.1.0-beta.6", "the counter continues from the existing 9.1.0 beta"

    def test_it_follows_a_major_release_rather_than_resetting(self, tmp_path):
        code, version, output = _compute_beta_version(["v9.1.0", "v10.0.0"], tmp_path)
        assert code == 0, output
        assert version == "10.1.0-beta.1"

    def test_minors_compare_numerically_not_lexically(self, tmp_path):
        # A string sort puts 9.9.0 above 9.10.0 and would target 9.10.0 again,
        # publishing a beta at a version already released.
        code, version, output = _compute_beta_version(["v9.9.0", "v9.10.0"], tmp_path)
        assert code == 0, output
        assert version == "9.11.0-beta.1"

    def test_an_override_wins_so_a_breaking_cycle_can_say_so(self, tmp_path):
        # A derivation can only add a minor. Installs graduate off betas by
        # version comparison (#1992), so a cycle heading for 10.0.0 has to be
        # able to number its betas 10.0.0-beta.N.
        code, version, output = _compute_beta_version(["v9.0.0", "v9.1.0"], tmp_path, override="10.0.0")
        assert code == 0, output
        assert version == "10.0.0-beta.1"

    def test_a_stale_override_fails_loudly_rather_than_publishing_below_a_release(self, tmp_path):
        code, version, output = _compute_beta_version(["v9.0.0", "v9.1.0"], tmp_path, override="9.0.0")
        assert code != 0
        assert version is None
        assert "already released" in output

    def test_a_malformed_override_is_rejected(self, tmp_path):
        code, _version, output = _compute_beta_version(["v9.0.0"], tmp_path, override="9.1")
        assert code != 0
        assert "not X.Y.Z" in output

    def test_no_stable_tag_is_an_error_not_a_silent_zero(self, tmp_path):
        # Without fetch-tags the checkout brings none, and a silent fallback
        # would publish a beta numbered off nothing.
        code, version, output = _compute_beta_version(["v9.0.0-beta.1"], tmp_path)
        assert code != 0
        assert version is None
        assert "No stable" in output

    def test_the_workflow_declares_no_hardcoded_target(self):
        """The literal is what went stale; its absence is the fix."""
        import re

        text = BETA.read_text(encoding="utf-8")
        assert not re.search(r'BETA_TARGET_VERSION:\s*"', text), (
            "release-beta.yml declares a hardcoded BETA_TARGET_VERSION again. "
            "The target is derived from the newest stable tag; use "
            "BETA_TARGET_OVERRIDE for a breaking cycle instead."
        )
        # Empty on a normal cycle, so the derivation sets the version. A
        # breaking cycle sets an explicit X.Y.Z, as the workflow's own comment
        # prescribes (the derivation can add a minor, never a major); the
        # step's runtime assert then refuses a target at or below a release.
        assert re.search(r'BETA_TARGET_OVERRIDE:\s*"(\d+\.\d+\.\d+)?"\s*$', text, re.M), (
            "BETA_TARGET_OVERRIDE should be present, and either empty (normal cycle: derived target) "
            'or an explicit "X.Y.Z" for a breaking cycle.'
        )

    def test_the_computing_job_fetches_tags(self):
        """The derivation reads tags; a checkout without them finds nothing."""
        owner = None
        for name, job in _load(BETA)["jobs"].items():
            for step in job.get("steps", []):
                if step.get("id") == "version":
                    owner = name
        assert owner, "no job owns the version step"
        checkouts = [
            s for s in _load(BETA)["jobs"][owner]["steps"] if str(s.get("uses", "")).startswith("actions/checkout")
        ]
        assert checkouts, f"job {owner} does not check out the repository"
        assert any(
            (c.get("with") or {}).get("fetch-tags") or (c.get("with") or {}).get("fetch-depth") == 0 for c in checkouts
        ), f"job {owner} checks out without tags, so the beta target would derive from an empty tag list"


class TestBetaCounter:
    """The beta number counts from 1 within each target version.

    It used to be `github.run_number`, which never resets, so the first beta
    after 9.6.1 would have been 9.7.0-beta.51. The counter is now the highest
    number already used for that target, plus one.
    """

    def test_the_first_beta_of_a_new_target_is_beta_1(self, tmp_path):
        code, version, output = _compute_beta_version(["v9.6.1", "v9.3.0-beta.50"], tmp_path)
        assert code == 0, output
        assert version == "9.7.0-beta.1"

    def test_it_counts_up_from_the_last_beta_of_the_same_target(self, tmp_path):
        code, version, output = _compute_beta_version(["v9.6.1", "v9.7.0-beta.1", "v9.7.0-beta.2"], tmp_path)
        assert code == 0, output
        assert version == "9.7.0-beta.3"

    def test_betas_of_other_targets_do_not_advance_the_counter(self, tmp_path):
        code, version, output = _compute_beta_version(
            ["v9.6.1", "v9.6.0-beta.40", "v9.7.0-beta.2", "v9.17.0-beta.30"], tmp_path
        )
        assert code == 0, output
        assert version == "9.7.0-beta.3"

    def test_numbers_compare_numerically_not_lexically(self, tmp_path):
        # A string sort puts beta.9 above beta.10 and would publish beta.10 twice.
        code, version, output = _compute_beta_version(["v9.6.1", "v9.7.0-beta.9", "v9.7.0-beta.10"], tmp_path)
        assert code == 0, output
        assert version == "9.7.0-beta.11"

    def test_a_number_already_on_docker_hub_is_not_reused(self, tmp_path):
        """The image is pushed before its git tag is created.

        A run that failed between the two left `9.7.0-beta.3` on Docker Hub
        with no git tag. Reusing the number would overwrite that image.
        """
        code, version, output = _compute_beta_version(
            ["v9.6.1", "v9.7.0-beta.2"], tmp_path, registry_tags=("beta", "9.7.0-beta.3", "9.3.0-beta.50")
        )
        assert code == 0, output
        assert version == "9.7.0-beta.4"


def test_no_job_reads_the_version_from_a_step_it_does_not_own():
    """`steps.version.outputs` is empty in any job but the one that ran it.

    This is not hypothetical. The first published beta created its GitHub
    release with tag `v` and name `Beta ` — an empty version string — because
    the release step still said `steps.version.outputs.version` after the
    workflow was split into version/build/publish jobs. The Docker tags were
    already on `needs.` and came out correct, so the image published fine and
    every job reported success; only the release was malformed. GitHub does
    not error on an unresolvable expression, it substitutes empty.
    """
    import re

    text = BETA.read_text(encoding="utf-8")
    doc = _load(BETA)

    owner = None
    for name, job in doc["jobs"].items():
        for step in job.get("steps", []):
            if step.get("id") == "version":
                owner = name
    assert owner, "no job declares a step with id 'version'"

    # Split the file into per-job regions so a reference can be attributed.
    job_starts = sorted((m.start(), m.group(1)) for m in re.finditer(r"^  ([a-z][\w-]*):\s*$", text, re.MULTILINE))
    offenders = []
    for m in re.finditer(r"steps\.version\.outputs", text):
        job = next((n for pos, n in reversed(job_starts) if pos < m.start()), "?")
        if job != owner:
            offenders.append(job)
    assert not offenders, (
        f"jobs {sorted(set(offenders))} read `steps.version.outputs`, but the "
        f"version step runs in {owner!r}. Cross-job reads must use "
        f"`needs.{owner}.outputs.version` — an unresolvable expression "
        f"silently becomes an empty string, which is how beta.1 shipped a "
        f"release tagged `v`."
    )
