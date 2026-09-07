"""Every Playwright spec must actually be run by some workflow (issue #1737).

A test job that never runs is worse than no job at all: it reads as green
coverage on the PR page while asserting nothing. This repo has hit that twice
--- all four E2E jobs were gated on ``pull_request`` so the merge queue skipped
them 28/28 (#1771), and ``ingress.spec.ts`` sat behind a ``RUN_INGRESS_TESTS``
flag with no job to set it. Both were found by hand, months later.

These tests close the loop mechanically. They read
``web/playwright.config.ts`` for the env-gated ignore lists and every
``npx playwright test`` invocation in ``.github/workflows/``, then assert:

1. every spec in ``web/tests/`` is executed by at least one invocation;
2. every ``RUN_*`` gate the config defines is actually set by some job;
3. every spec is reachable by an invocation that can run on ``merge_group``,
   so the queue --- the last gate before ``main`` --- really tests it.

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
    runs_on_merge_queue: bool


# --------------------------------------------------------------------------
# playwright.config.ts
# --------------------------------------------------------------------------


def _quoted_strings(fragment: str) -> list[str]:
    return re.findall(r'"([^"]+)"', fragment)


def parse_ignore_rules() -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Return (always-in-CI ignores, {env gate: globs}, always ignores).

    * *always-in-CI ignores* come from the initial ``const ciIgnore = [...]``.
    * *env gates* are the ``if (!process.env.X) { ciIgnore.push(...) }`` blocks:
      those globs are ignored unless ``X`` is set.
    * *always ignores* are the literal globs in ``testIgnore``, applied
      regardless of ``CI``.
    """
    source = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")

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


def _admits_merge_group(condition: Any) -> bool:
    """Whether a job/step ``if:`` can be true for a ``merge_group`` event.

    Conservative on purpose: no condition means it always runs; a condition
    that mentions ``merge_group`` is assumed to admit it; anything else (say
    ``github.event_name == 'pull_request'``) is assumed not to. A wrong guess
    here fails the test rather than passing it silently.
    """
    if condition is None:
        return True
    return "merge_group" in str(condition)


def _spec_args(command: str) -> tuple[str, ...]:
    """Extract explicit spec-file arguments from a playwright command line."""
    match = re.search(r"playwright\s+test\b(?P<rest>[^\n]*)", command)
    if not match:
        return ()
    args = []
    for token in match.group("rest").split():
        if token.startswith("-"):
            continue
        args.append(token)
    return tuple(args)


def collect_invocations() -> list[Invocation]:
    invocations: list[Invocation] = []
    for workflow_path in sorted(WORKFLOW_DIR.glob("*.yml")):
        data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        # PyYAML parses the bare key `on:` as the boolean True.
        triggers = data.get("on", data.get(True)) or {}
        workflow_has_merge_group = "merge_group" in (triggers if isinstance(triggers, dict) else {triggers: None})

        for job_name, job in (data.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            job_admits = workflow_has_merge_group and _admits_merge_group(job.get("if"))
            job_env = {str(k): str(v) for k, v in (job.get("env") or {}).items()}

            for step in job.get("steps") or []:
                command = str(step.get("run") or "")
                if "playwright test" not in command:
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
                        runs_on_merge_queue=job_admits and _admits_merge_group(step.get("if")),
                    )
                )
    return invocations


# --------------------------------------------------------------------------
# reachability
# --------------------------------------------------------------------------


def _ignored_globs_for(invocation: Invocation) -> list[str]:
    base, gates, always = parse_ignore_rules()
    ignored = list(always)
    # Workflow steps always run with CI set, so the CI-only list applies.
    ignored += base
    for env_var, globs in gates.items():
        if not invocation.env.get(env_var):
            ignored += globs
    return ignored


def _runs(spec_rel: str, invocation: Invocation) -> bool:
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
    assert len(collect_invocations()) >= 4, "Found fewer `playwright test` workflow steps than the four E2E jobs"


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


def test_every_spec_is_gated_on_the_merge_queue():
    """The queue is the last gate before main; it must run every spec.

    A PR-only E2E job tests the PR head, never the merged result — two
    individually-green PRs can then land a semantic conflict that surfaces as
    an "unrelated" failure on whatever branch rebases next. This is the
    regression guard for #1771 and #1737.
    """
    gaps = sorted(
        spec for spec, invs in _reachability_map().items() if invs and not any(inv.runs_on_merge_queue for inv in invs)
    )
    assert not gaps, (
        "These specs run on pull_request but not in the merge queue, so the queue "
        "cannot gate on them:\n  "
        + "\n  ".join(gaps)
        + "\n\nAdd `merge_group` to the owning workflow's `on:` and to the job's `if:`."
    )
