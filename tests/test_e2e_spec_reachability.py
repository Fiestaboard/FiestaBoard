"""Every Playwright spec must actually be run by some workflow (issue #1737).

A test job that never runs is worse than no job at all: it reads as green
coverage on the PR page while asserting nothing. This repo has hit that twice
--- all four E2E jobs were gated on ``pull_request`` so the old merge queue
skipped them 28/28 (#1771), and ``ingress.spec.ts`` sat behind a ``RUN_INGRESS_TESTS``
flag with no job to set it. Both were found by hand, months later.

These tests close the loop mechanically. They read
``web/playwright.config.ts`` for the env-gated ignore lists and every
``npx playwright test`` invocation in ``.github/workflows/``, then assert:

1. every spec in ``web/tests/`` is executed by at least one invocation;
2. every ``RUN_*`` gate the config defines is actually set by some job;
3. every spec is reachable by an invocation that runs on the Changesets
   Version PR (head ``changeset-release/*``). That PR is rebuilt on every
   push to its base branch, so its head is the merged result of everything
   about to ship; it is the last gate before a release, the job the merge
   queue used to do.

The parsing is deliberately shallow (regex over the TS config, YAML over the
workflows). If either file changes shape enough to break the parse, these
tests fail loudly rather than passing on an empty result set --- see
``test_parsers_found_something``.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any, NamedTuple

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SPEC_DIR = REPO_ROOT / "web" / "tests"
PLAYWRIGHT_CONFIG = REPO_ROOT / "web" / "playwright.config.ts"

# Specs that are intentionally not run by any CI workflow, with the reason.
# This allowlist is asserted to be *minimal*: an entry that has since become
# reachable fails the test, so it can't rot into a blanket exemption.
INTENTIONALLY_UNREACHABLE = {
    "generate-screenshots.spec.ts": "Authoring tool — regenerates documentation screenshots on demand, not a test.",
    "draw-mode-demo.spec.ts": "Authoring tool — records the draw-mode demo GIF, excluded even locally.",
}


class Invocation(NamedTuple):
    """One ``npx playwright test`` step found in a workflow."""

    workflow: str
    job: str
    step: str
    specs: tuple[str, ...]  # explicit file args; empty means "the whole suite"
    env: dict[str, str]
    runs_on_version_pr: bool
    config: Path = PLAYWRIGHT_CONFIG


# --------------------------------------------------------------------------
# playwright.config.ts
# --------------------------------------------------------------------------


def _quoted_strings(fragment: str) -> list[str]:
    return re.findall(r'"([^"]+)"', fragment)


def parse_ignore_rules(config: Path = PLAYWRIGHT_CONFIG) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Return (always-in-CI ignores, {env gate: globs}, always ignores).

    * *always-in-CI ignores* come from the initial ``const ciIgnore = [...]``.
    * *env gates* are the ``if (!process.env.X) { ciIgnore.push(...) }`` blocks:
      those globs are ignored unless ``X`` is set.
    * *always ignores* are the literal globs in ``testIgnore``, applied
      regardless of ``CI``.
    """
    source = config.read_text(encoding="utf-8")

    base_match = re.search(r"const ciIgnore\s*=\s*\[([^\]]*)\]", source)
    base = _quoted_strings(base_match.group(1)) if base_match else []

    gates: dict[str, list[str]] = {}
    for env_var, pushed in re.findall(
        r"if\s*\(!process\.env\.(\w+)\)\s*\{\s*ciIgnore\.push\(([^)]*)\)",
        source,
    ):
        gates.setdefault(env_var, []).extend(_quoted_strings(pushed))

    ignore_match = re.search(r"testIgnore:\s*\[(.*?)\]\s*,", source, re.DOTALL)
    always = _quoted_strings(ignore_match.group(1)) if ignore_match else []

    return base, gates, always


def _matches(spec_path: str, glob: str) -> bool:
    """Match a repo-relative spec path against a playwright ignore glob."""
    return fnmatch.fnmatch(spec_path, glob.removeprefix("**/")) or fnmatch.fnmatch(
        Path(spec_path).name, glob.removeprefix("**/")
    )


# --------------------------------------------------------------------------
# .github/workflows/*.yml
# --------------------------------------------------------------------------


# Files every Version PR changes: `changeset version` bumps the root
# package.json, and scripts/version-sync.js copies the version into the rest.
VERSION_PR_FILES = ("package.json", "web/package.json", "src/__init__.py")

_VERSION_PR_HEAD = "startsWith(github.head_ref, 'changeset-release/')"
# The path gate ci.yml's test jobs share. The Version PR always trips it,
# because `shared` lists package.json (see test_version_pr_trips_the_shared_filter).
_SHARED_PATH_GATE = "needs.detect-changes.outputs.shared == 'true'"


def _admits_version_pr(condition: Any) -> bool:
    """Whether a job/step ``if:`` can be true on the Version PR.

    Conservative on purpose: no condition means it always runs, and only
    known forms are recognised --- an explicit ``changeset-release/`` head
    check, or ci.yml's path gate that includes ``shared``. Anything else
    (say ``github.event_name == 'push'``) is assumed not to admit it. A wrong
    guess here fails the test rather than passing it silently.
    """
    if condition is None:
        return True
    text = str(condition).removeprefix("${{").removesuffix("}}").strip()
    # A per-suite readiness condition does not restrict the triggering event.
    # Recognize only this known form; unknown expressions stay conservative.
    if re.fullmatch(r"!cancelled\(\)\s*&&\s*steps\.[\w-]+\.outcome\s*==\s*'success'", text):
        return True
    if "!" + _VERSION_PR_HEAD in text:
        return False
    return _VERSION_PR_HEAD in text or _SHARED_PATH_GATE in text


def _pull_request_reaches_version_pr(triggers: Any) -> bool:
    """Whether the workflow's ``pull_request`` trigger fires for a Version PR."""
    if not isinstance(triggers, dict):
        triggers = dict.fromkeys(triggers if isinstance(triggers, list) else [triggers])
    if "pull_request" not in triggers:
        return False
    paths = (triggers["pull_request"] or {}).get("paths")
    if not paths:
        return True
    return any(fnmatch.fnmatch(f, glob) for f in VERSION_PR_FILES for glob in paths)


def _spec_args(command: str) -> tuple[str, ...]:
    """Extract explicit spec-file arguments from a playwright command line."""
    match = re.search(r"playwright\s+test\b(?P<rest>[^\n]*)", command)
    if not match:
        return ()
    args = []
    tokens = iter(match.group("rest").split())
    for token in tokens:
        if token in ("--config", "-c"):
            next(tokens, None)
            continue
        if token.startswith("-"):
            continue
        args.append(token)
    return tuple(args)


def _invocation_config(command: str) -> Path:
    match = re.search(r"(?:--config(?:=|\s+)|-c\s+)([^\s]+)", command)
    return REPO_ROOT / "web" / match.group(1) if match else PLAYWRIGHT_CONFIG


def collect_invocations() -> list[Invocation]:
    invocations: list[Invocation] = []
    for workflow_path in sorted(WORKFLOW_DIR.glob("*.yml")):
        data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        # PyYAML parses the bare key `on:` as the boolean True.
        triggers = data.get("on", data.get(True)) or {}
        workflow_reaches_version_pr = _pull_request_reaches_version_pr(triggers)

        for job_name, job in (data.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            job_admits = workflow_reaches_version_pr and _admits_version_pr(job.get("if"))
            job_env = {str(k): str(v) for k, v in (job.get("env") or {}).items()}

            for step in job.get("steps") or []:
                command = str(step.get("run") or "")
                if "playwright test" not in command:
                    continue
                config = _invocation_config(command)
                # Documentation captures are an authoring workflow, not a test gate.
                # Keep its dedicated config out of regression-test reachability.
                if config.name == "playwright-screenshots.config.ts":
                    continue
                env = dict(job_env)
                env.update({str(k): str(v) for k, v in (step.get("env") or {}).items()})
                invocations.append(
                    Invocation(
                        workflow=workflow_path.name,
                        job=str(job_name),
                        step=str(step.get("name") or command),
                        specs=_spec_args(command),
                        env=env,
                        runs_on_version_pr=job_admits and _admits_version_pr(step.get("if")),
                        config=config,
                    )
                )
    return invocations


# --------------------------------------------------------------------------
# reachability
# --------------------------------------------------------------------------


def _ignored_globs_for(invocation: Invocation) -> list[str]:
    base, gates, always = parse_ignore_rules(invocation.config)
    ignored = list(always)
    # Workflow steps always run with CI set, so the CI-only list applies.
    ignored += base
    for env_var, globs in gates.items():
        if not invocation.env.get(env_var):
            ignored += globs
    return ignored


def _runs(spec_rel: str, invocation: Invocation) -> bool:
    source = invocation.config.read_text(encoding="utf-8")
    test_dir = re.search(r'testDir:\s*"([^"]+)"', source)
    assert test_dir, f"No testDir parsed from {invocation.config}"
    root = (invocation.config.parent / test_dir.group(1)).resolve()
    if not (SPEC_DIR / spec_rel).resolve().is_relative_to(root):
        return False
    if any(_matches(spec_rel, glob) for glob in _ignored_globs_for(invocation)):
        return False
    if not invocation.specs:
        return True  # whole-suite run
    # Bare playwright args are path substring filters.
    return any(arg in spec_rel for arg in invocation.specs)


def all_specs() -> list[str]:
    return sorted(str(p.relative_to(SPEC_DIR)) for p in SPEC_DIR.rglob("*.spec.ts"))


def _reachability_map() -> dict[str, list[Invocation]]:
    invocations = collect_invocations()
    return {spec: [inv for inv in invocations if _runs(spec, inv)] for spec in all_specs()}


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------


def test_parsers_found_something():
    """A broken parse must fail here, not silently pass every other test."""
    base, gates, always = parse_ignore_rules()
    assert gates, f"No `if (!process.env.X) ciIgnore.push(...)` gates parsed from {PLAYWRIGHT_CONFIG}"
    assert base or always, f"No testIgnore globs parsed from {PLAYWRIGHT_CONFIG}"
    assert len(all_specs()) > 40, "Spec discovery found suspiciously few files"
    assert len(collect_invocations()) >= 4, "Found fewer `playwright test` workflow steps than the required E2E suites"


def test_every_spec_is_run_by_some_workflow():
    """No spec sits in the tree unreachable by every workflow."""
    unreachable = sorted(spec for spec, invs in _reachability_map().items() if not invs)
    unexpected = [spec for spec in unreachable if Path(spec).name not in INTENTIONALLY_UNREACHABLE]
    assert not unexpected, (
        "These specs are not executed by any workflow — they read as coverage but assert nothing:\n  "
        + "\n  ".join(unexpected)
        + "\n\nEither wire them into a CI job or delete them. If a spec is an authoring "
        "tool rather than a test, add it to INTENTIONALLY_UNREACHABLE with a reason."
    )


def test_unreachable_allowlist_is_minimal():
    """An allowlisted spec that CI now runs must leave the allowlist."""
    reachable = {Path(spec).name for spec, invs in _reachability_map().items() if invs}
    stale = sorted(reachable & set(INTENTIONALLY_UNREACHABLE))
    assert not stale, (
        "These specs are listed in INTENTIONALLY_UNREACHABLE but a workflow does run them; "
        f"drop them from the allowlist: {stale}"
    )


def test_every_env_gate_is_set_by_some_job():
    """Every `RUN_*` opt-in in playwright.config.ts has a job that sets it."""
    _, gates, _ = parse_ignore_rules()
    invocations = collect_invocations()
    orphans = sorted(env_var for env_var in gates if not any(inv.env.get(env_var) for inv in invocations))
    assert not orphans, (
        "These env gates hide specs from every CI run because no workflow sets them: "
        f"{orphans}. Wire a job that sets the flag, or remove the gate and the specs behind it."
    )


def test_every_spec_is_gated_on_the_version_pr():
    """The Version PR is the last gate before a release; it must run every spec.

    A PR-only E2E job tests the PR head, never the merged result --- two
    individually-green PRs can then land a semantic conflict. The Version PR
    is rebuilt on its base branch's tip, so it is where the merged result gets
    tested before it ships. This is the regression guard for #1771 and #1737.
    """
    gaps = sorted(
        spec for spec, invs in _reachability_map().items() if invs and not any(inv.runs_on_version_pr for inv in invs)
    )
    assert not gaps, (
        "These specs run on some pull requests but not on the Version PR, so a "
        "release cannot gate on them:\n  "
        + "\n  ".join(gaps)
        + "\n\nMake the owning job's `if:` admit a `changeset-release/*` head ref."
    )


def test_version_pr_trips_the_shared_filter():
    """ci.yml's test jobs reach the Version PR only through the `shared` filter."""
    ci = yaml.safe_load((WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8"))
    step = next(s for s in ci["jobs"]["detect-changes"]["steps"] if s.get("id") == "filter")
    shared = yaml.safe_load(step["with"]["filters"])["shared"]
    assert any(fnmatch.fnmatch(f, glob) for f in VERSION_PR_FILES for glob in shared)


def test_full_integration_suite_runs_on_the_version_pr():
    """The 4-backend integration suite used to run only in the merge queue."""
    full = [inv for inv in collect_invocations() if inv.workflow == "integration-tests.yml" and not inv.specs]
    assert len(full) == 1
    assert full[0].runs_on_version_pr


def test_no_workflow_still_waits_for_a_merge_queue():
    """main has no merge queue; a `merge_group` trigger or gate is dead config."""
    stale = sorted(p.name for p in WORKFLOW_DIR.glob("*.yml") if "merge_group" in p.read_text(encoding="utf-8"))
    assert not stale, f"These workflows still reference merge_group: {stale}"


def test_config_arguments_are_not_spec_filters():
    assert _spec_args("npx playwright test --config tests/layout/playwright.config.ts") == ()


def test_layout_spec_is_reached_only_through_its_own_config():
    invocations = collect_invocations()
    layout = [inv for inv in invocations if inv.step == "Browser layout regressions"]
    assert len(layout) == 1
    assert _runs("layout/preview.spec.ts", layout[0])
    assert not _runs("draw-mode.spec.ts", layout[0])
    regular = [inv for inv in invocations if inv.step != "Browser layout regressions"]
    assert not any(_runs("layout/preview.spec.ts", inv) for inv in regular)


def test_readiness_guards_do_not_hide_version_pr_tests():
    assert _admits_version_pr("${{ !cancelled() && steps.ai_ready_2.outcome == 'success' }}")
    assert not _admits_version_pr("github.event_name == 'push'")
    assert not _admits_version_pr(
        "!cancelled() && steps.ai_ready_2.outcome == 'success' && github.event_name == 'pull_request'"
    )
    assert not _admits_version_pr("env.UNKNOWN_GATE == '1'")


def test_version_pr_head_check_is_recognised_only_unnegated():
    assert _admits_version_pr("startsWith(github.head_ref, 'changeset-release/')")
    assert not _admits_version_pr("!startsWith(github.head_ref, 'changeset-release/')")


def test_path_filtered_workflows_must_match_a_version_pr_file():
    assert _pull_request_reaches_version_pr({"pull_request": {"paths": ["web/**"]}})
    assert not _pull_request_reaches_version_pr({"pull_request": {"paths": ["docs/**"]}})
    assert not _pull_request_reaches_version_pr({"push": None})


def test_device_sign_in_has_a_dedicated_version_pr_gate():
    invocations = collect_invocations()
    device = [inv for inv in invocations if inv.config.name == "playwright.device.config.ts"]
    assert len(device) == 1
    assert device[0].runs_on_version_pr
    assert _runs("device-sign-in.spec.ts", device[0])
    assert not any(
        _runs("device-sign-in.spec.ts", inv) for inv in invocations if inv.config.name != "playwright.device.config.ts"
    )
