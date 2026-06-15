#!/usr/bin/env python3
"""Programmatic grader for new-claude-github-actions-flow evals.

Reads an iteration directory, runs each eval's assertions against its
outputs, writes grading.json per run with {text, passed, evidence}.

Usage:
    python3 grade.py <iteration_dir>
    e.g. python3 grade.py .../iteration-1/
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def read(p: Path) -> str:
    try:
        return p.read_text()
    except (FileNotFoundError, UnicodeDecodeError):
        return ""


def strip_yaml_comments(text: str) -> str:
    """Strip lines that are pure YAML comments so checks like 'pull-requests: write'
    don't match comment text that merely mentions the literal."""
    return "\n".join(ln for ln in text.splitlines() if not re.match(r"^\s*#", ln))


def files_under(d: Path) -> list[Path]:
    return [p for p in d.rglob("*") if p.is_file()]


# -----------------------------------------------------------------------------
# Generic checks shared across evals
# -----------------------------------------------------------------------------

def grep(pattern: str, text: str, flags: int = 0) -> tuple[bool, str]:
    """Return (matched, snippet around first match or empty)."""
    m = re.search(pattern, text, flags)
    if not m:
        return False, ""
    start = max(0, m.start() - 60)
    end = min(len(text), m.end() + 60)
    snippet = text[start:end].replace("\n", "\\n")
    return True, f"…{snippet}…"


def all_grep(patterns: list[str], text: str, flags: int = 0) -> tuple[bool, str]:
    misses = [p for p in patterns if not re.search(p, text, flags)]
    if misses:
        return False, f"missing: {misses}"
    return True, f"all {len(patterns)} patterns matched"


# -----------------------------------------------------------------------------
# Eval 1 — create tests-audit
# -----------------------------------------------------------------------------

def grade_eval_1(outputs: Path) -> list[dict]:
    """Grade the create-tests-audit-from-scratch eval."""
    audit = read(outputs / ".github/workflows/claude-tests-audit.yml")
    review = read(outputs / ".github/workflows/claude-tests-audit-review.yml")
    feedback = read(outputs / ".github/workflows/claude-tests-audit-feedback.yml")
    state = read(outputs / ".github/tests-audit-state.json")
    rejection = read(outputs / ".github/tests-audit/build_rejection.py")
    feedback_readme = read(outputs / ".github/tests-audit/README.md")
    triage = read(outputs / ".github/workflows/claude-issue-triage.yml")

    def check(text: str, fn) -> tuple[bool, str]:
        return fn(text)

    results = []

    def add(text: str, passed: bool, evidence: str):
        results.append({"text": text, "passed": passed, "evidence": evidence[:300]})

    # --- audit workflow ---
    if not audit:
        for t in [
            "audit workflow uses BRANCH_SUFFIX env var bound to github.run_id (not date +%s)",
            "audit workflow sets show_full_output: 'true' on the claude-code-action",
            "audit workflow's --allowed-tools includes Edit, Write, Bash(git push:*), and Bash(gh pr create:*)",
            "audit workflow has at least 4 cron entries arranged as UTC pairs for DST absorption",
            "audit workflow declares concurrency group with cancel-in-progress: false",
            "audit workflow uses RELEASE_PAT for the checkout token to push past branch protection",
            "audit workflow includes Compute dynamic effort step with three modes (thorough/balanced/conservative)",
            "audit workflow's Dedup step has both cooldown-hours and draft-cap checks",
            "audit workflow has a local-hour time gate (TZ=America/Los_Angeles) before checkout",
            "audit workflow's prompt instructs Claude to read the rejection log before doing anything else",
            "audit workflow's hard rules section restricts editable files to tests-only globs",
            "audit workflow's prompt covers all three user-specified checks: flaky tests, slow tests, no-assertion tests",
        ]:
            add(t, False, "audit workflow file missing")
    else:
        ok, ev = grep(r"BRANCH_SUFFIX:\s*\$\{\{\s*github\.run_id\s*\}\}", audit)
        add("audit workflow uses BRANCH_SUFFIX env var bound to github.run_id (not date +%s)", ok, ev)

        ok, ev = grep(r"show_full_output:\s*['\"]?true['\"]?", audit)
        add("audit workflow sets show_full_output: 'true' on the claude-code-action", ok, ev)

        ok, ev = all_grep([r"Edit", r"Write", r"Bash\(git push", r"Bash\(gh pr create"], audit)
        add("audit workflow's --allowed-tools includes Edit, Write, Bash(git push:*), and Bash(gh pr create:*)", ok, ev)

        cron_count = len(re.findall(r"^\s*-\s*cron:", audit, re.MULTILINE))
        add(
            "audit workflow has at least 4 cron entries arranged as UTC pairs for DST absorption",
            cron_count >= 4,
            f"cron count = {cron_count}",
        )

        ok, ev = grep(r"cancel-in-progress:\s*false", audit)
        add("audit workflow declares concurrency group with cancel-in-progress: false", ok, ev)

        ok, ev = grep(r"RELEASE_PAT", audit)
        add("audit workflow uses RELEASE_PAT for the checkout token to push past branch protection", ok, ev)

        ok, ev = all_grep([r"thorough", r"balanced", r"conservative"], audit)
        add("audit workflow includes Compute dynamic effort step with three modes (thorough/balanced/conservative)", ok, ev)

        ok, ev = all_grep([r"cooldown", r"draft_count"], audit, re.IGNORECASE)
        add("audit workflow's Dedup step has both cooldown-hours and draft-cap checks", ok, ev)

        ok, ev = grep(r"TZ=America/Los_Angeles", audit)
        add("audit workflow has a local-hour time gate (TZ=America/Los_Angeles) before checkout", ok, ev)

        ok, ev = grep(r"rejected-edits\.jsonl", audit)
        add("audit workflow's prompt instructs Claude to read the rejection log before doing anything else", ok, ev)

        ok, ev = grep(r"tests/.*\.py|\*\.py", audit)
        add("audit workflow's hard rules section restricts editable files to tests-only globs", ok, ev)

        ok, ev = all_grep([r"flak", r"slow", r"assert"], audit, re.IGNORECASE)
        add("audit workflow's prompt covers all three user-specified checks: flaky tests, slow tests, no-assertion tests", ok, ev)

    # --- review workflow ---
    if not review:
        for t in [
            "auto-review workflow uses pull_request_target (not pull_request)",
            "auto-review workflow checks out base.ref (never head.ref) with persist-credentials: false",
            "auto-review workflow passes github_token: secrets.GITHUB_TOKEN to bypass OIDC App exchange",
            "auto-review workflow's allowed_bots includes both claude and github-actions",
            "auto-review workflow's --allowed-tools is read-only (no Edit, no Write, no git push, no gh pr create)",
        ]:
            add(t, False, "review workflow file missing")
    else:
        ok, ev = grep(r"pull_request_target", review)
        add("auto-review workflow uses pull_request_target (not pull_request)", ok, ev)

        base_ok, _ = grep(r"github\.event\.pull_request\.base\.ref", review)
        head_used, _ = grep(r"head\.sha\s*\}\}\s*\n.*ref:\s*\$\{\{\s*github\.event\.pull_request\.head", review)
        persist, _ = grep(r"persist-credentials:\s*false", review)
        add(
            "auto-review workflow checks out base.ref (never head.ref) with persist-credentials: false",
            base_ok and persist and not head_used,
            f"base.ref ok={base_ok}, persist-credentials:false={persist}, head.ref used in checkout={head_used}",
        )

        ok, ev = grep(r"github_token:\s*\$\{\{\s*secrets\.GITHUB_TOKEN", review)
        add("auto-review workflow passes github_token: secrets.GITHUB_TOKEN to bypass OIDC App exchange", ok, ev)

        ok, ev = grep(r"allowed_bots:.*claude.*github-actions|allowed_bots:.*github-actions.*claude", review)
        add("auto-review workflow's allowed_bots includes both claude and github-actions", ok, ev)

        # The allowlist string for review must not contain write-y patterns
        m = re.search(r"--allowed-tools\s+\"([^\"]+)\"", review)
        if m:
            tools = m.group(1)
            forbidden = [w for w in [r"\bEdit\b", r"\bWrite\b", r"git push", r"gh pr create"] if re.search(w, tools)]
            add(
                "auto-review workflow's --allowed-tools is read-only (no Edit, no Write, no git push, no gh pr create)",
                not forbidden,
                f"forbidden found: {forbidden}; tools={tools[:200]}",
            )
        else:
            add(
                "auto-review workflow's --allowed-tools is read-only (no Edit, no Write, no git push, no gh pr create)",
                False,
                "no --allowed-tools found in review workflow",
            )

    # --- feedback workflow ---
    if not feedback:
        for t in [
            "feedback workflow uses pull_request_target on closed event (not pull_request)",
            "feedback workflow's if-condition checks startsWith for BOTH the audit branch prefix and the triage branch prefix",
            "feedback workflow's concurrency has cancel-in-progress: false to serialize log writes",
        ]:
            add(t, False, "feedback workflow file missing")
    else:
        ok, ev = grep(r"pull_request_target:[^\n]*\n\s*types:\s*\[closed\]", feedback)
        add("feedback workflow uses pull_request_target on closed event (not pull_request)", ok, ev)

        starts = re.findall(r"startsWith\(github\.event\.pull_request\.head\.ref,\s*'([^']+)'\)", feedback)
        add(
            "feedback workflow's if-condition checks startsWith for BOTH the audit branch prefix and the triage branch prefix",
            len(starts) >= 2,
            f"startsWith prefixes found: {starts}",
        )

        ok, ev = grep(r"cancel-in-progress:\s*false", feedback)
        add("feedback workflow's concurrency has cancel-in-progress: false to serialize log writes", ok, ev)

    # --- build_rejection.py ---
    if not rejection:
        add(
            "build_rejection.py present, idempotent (replaces prior line for same PR), refuses to log merged PRs",
            False, "build_rejection.py missing",
        )
    else:
        ok, ev = all_grep([r"keep", r"MERGED", r"def\s+build_record"], rejection)
        add(
            "build_rejection.py present, idempotent (replaces prior line for same PR), refuses to log merged PRs",
            ok, ev,
        )

    # --- state json ---
    if not state:
        add("state JSON file initialized with schema_version: 1, round: 0, empty files arrays", False, "state file missing")
    else:
        try:
            j = json.loads(state)
            ok = (
                j.get("schema_version") == 1
                and j.get("round") == 0
                and j.get("files_remaining") == []
                and j.get("files_audited") == []
            )
            add(
                "state JSON file initialized with schema_version: 1, round: 0, empty files arrays",
                ok,
                f"schema_version={j.get('schema_version')} round={j.get('round')} remaining_len={len(j.get('files_remaining', []))} audited_len={len(j.get('files_audited', []))}",
            )
        except json.JSONDecodeError:
            add("state JSON file initialized with schema_version: 1, round: 0, empty files arrays", False, "invalid JSON")

    # --- feedback README ---
    if not feedback_readme:
        add("feedback dir has a README explaining the rejection log schema and DRY_RUN usage", False, "README missing")
    else:
        ok, ev = all_grep([r"rejected-edits\.jsonl", r"DRY_RUN", r"head_ref"], feedback_readme)
        add("feedback dir has a README explaining the rejection log schema and DRY_RUN usage", ok, ev)

    # --- triage workflow modified ---
    if not triage:
        add("triage workflow modified to add tests-audit label to the labeled-gate if-condition", False, "triage workflow not in outputs")
    else:
        ok, ev = grep(r"['\"]tests-audit['\"]", triage)
        add("triage workflow modified to add tests-audit label to the labeled-gate if-condition", ok, ev)

    return results


# -----------------------------------------------------------------------------
# Eval 2 — tune docs-audit
# -----------------------------------------------------------------------------

def grade_eval_2(outputs: Path) -> list[dict]:
    audit = read(outputs / ".github/workflows/claude-docs-audit.yml")
    summary = read(outputs / "summary.md")
    results = []

    def add(text: str, passed: bool, evidence: str):
        results.append({"text": text, "passed": passed, "evidence": evidence[:300]})

    if not audit:
        for t in [
            "claude-docs-audit.yml's conservative branch threshold changed from 80 to 40 (i.e., open_count -gt 40 triggers conservative)",
            "claude-docs-audit.yml's conservative batch is now 8 (was 12)",
            "claude-docs-audit.yml's conservative cap is now 20 (was 32)",
            "claude-docs-audit.yml's cooldown check is now `age_h -lt 6` (was 3)",
            "claude-docs-audit.yml's balanced and thorough branches were NOT changed (batches stay 24 and 32, caps stay 60 and 100)",
            "claude-docs-audit.yml's structure outside the 'Compute dynamic effort' and 'Dedup' steps was preserved (no incidental rewrites)",
        ]:
            add(t, False, "claude-docs-audit.yml missing from outputs")
    else:
        # Conservative threshold: looking for `if [ "$open_count" -gt 40 ];` as the first branch (replacing 80)
        # The pattern in the existing file is: `if [ "$open_count" -gt 80 ]; then\n    mode="conservative"`
        m = re.search(r'open_count"?\s*-gt\s+(\d+)\s*\]?\s*;\s*then\s*\n\s*mode="conservative"', audit)
        thresh = int(m.group(1)) if m else None
        add(
            "claude-docs-audit.yml's conservative branch threshold changed from 80 to 40 (i.e., open_count -gt 40 triggers conservative)",
            thresh == 40, f"conservative threshold = {thresh}",
        )

        m = re.search(r'mode="conservative";\s*batch=(\d+);\s*cap=(\d+)', audit)
        batch_c, cap_c = (int(m.group(1)), int(m.group(2))) if m else (None, None)
        add("claude-docs-audit.yml's conservative batch is now 8 (was 12)", batch_c == 8, f"conservative batch = {batch_c}")
        add("claude-docs-audit.yml's conservative cap is now 20 (was 32)", cap_c == 20, f"conservative cap = {cap_c}")

        m = re.search(r'age_h["\'\]\s]*-lt\s+(\d+)', audit)
        cool = int(m.group(1)) if m else None
        add(
            "claude-docs-audit.yml's cooldown check is now `age_h -lt 6` (was 3)",
            cool == 6, f"cooldown hours = {cool}",
        )

        # Balanced/thorough unchanged
        m_b = re.search(r'mode="balanced";\s*batch=(\d+);\s*cap=(\d+)', audit)
        m_t = re.search(r'mode="thorough";\s*batch=(\d+);\s*cap=(\d+)', audit)
        batch_b, cap_b = (int(m_b.group(1)), int(m_b.group(2))) if m_b else (None, None)
        batch_t, cap_t = (int(m_t.group(1)), int(m_t.group(2))) if m_t else (None, None)
        ok = batch_b == 24 and cap_b == 60 and batch_t == 32 and cap_t == 100
        add(
            "claude-docs-audit.yml's balanced and thorough branches were NOT changed (batches stay 24 and 32, caps stay 60 and 100)",
            ok, f"balanced=({batch_b},{cap_b}) thorough=({batch_t},{cap_t})",
        )

        # Structure preserved — check a few invariant phrases survive
        invariants = [
            "Gate on America/Los_Angeles local hour window",
            "Run Claude docs audit",
            "BRANCH_SUFFIX:",
            "show_full_output:",
            "anthropics/claude-code-action@v1",
            "concurrency:",
        ]
        misses = [p for p in invariants if p not in audit]
        add(
            "claude-docs-audit.yml's structure outside the 'Compute dynamic effort' and 'Dedup' steps was preserved (no incidental rewrites)",
            not misses, f"missing invariants: {misses}",
        )

    # Summary
    if not summary:
        add("summary.md describes before/after for each of the four knobs explicitly", False, "summary.md missing")
        add("summary.md includes a PR title and body draft", False, "summary.md missing")
    else:
        beforeAfter = sum(1 for tok in ["80", "40", "12", "8", "32", "20", " 3", " 6"] if tok in summary)
        add(
            "summary.md describes before/after for each of the four knobs explicitly",
            beforeAfter >= 6,
            f"matched {beforeAfter}/8 knob tokens",
        )

        ok, ev = grep(r"(?i)PR (title|body)", summary)
        add("summary.md includes a PR title and body draft", ok, ev)

    return results


# -----------------------------------------------------------------------------
# Eval 3 — minimal audit-only
# -----------------------------------------------------------------------------

def grade_eval_3(outputs: Path) -> list[dict]:
    audit = read(outputs / ".github/workflows/claude-manifest-audit.yml")
    state = read(outputs / ".github/manifest-audit-state.json")
    results = []

    def add(text: str, passed: bool, evidence: str):
        results.append({"text": text, "passed": passed, "evidence": evidence[:300]})

    all_files = files_under(outputs)
    rel = [str(p.relative_to(outputs)) for p in all_files]

    # exactly one workflow + one state json (ignoring summary.md)
    workflow_files = [p for p in rel if p.endswith(".yml") and "workflows/" in p]
    state_files = [p for p in rel if "state.json" in p]

    add(
        "exactly one workflow file created: .github/workflows/claude-manifest-audit.yml",
        workflow_files == [".github/workflows/claude-manifest-audit.yml"],
        f"workflow files: {workflow_files}",
    )
    add(
        "exactly one state file created: .github/manifest-audit-state.json",
        state_files == [".github/manifest-audit-state.json"],
        f"state files: {state_files}",
    )
    add(
        "NO review workflow file (claude-manifest-audit-review.yml) was created",
        ".github/workflows/claude-manifest-audit-review.yml" not in rel,
        "absent" if ".github/workflows/claude-manifest-audit-review.yml" not in rel else "present (should be absent)",
    )
    add(
        "NO feedback workflow file (claude-manifest-audit-feedback.yml) was created",
        ".github/workflows/claude-manifest-audit-feedback.yml" not in rel,
        "absent" if ".github/workflows/claude-manifest-audit-feedback.yml" not in rel else "present (should be absent)",
    )
    has_buildrejection = any("build_rejection" in p for p in rel)
    add(
        "NO build_rejection.py was created",
        not has_buildrejection,
        "absent" if not has_buildrejection else "present (should be absent)",
    )
    has_triage = any("issue-triage" in p for p in rel)
    add(
        "NO modifications were made to claude-issue-triage.yml",
        not has_triage,
        "absent" if not has_triage else "present (should be absent)",
    )

    if not audit:
        for t in [
            "audit workflow's --allowed-tools does NOT include Bash(gh pr create:*) (no PRs are opened)",
            "audit workflow's --allowed-tools does NOT include Bash(git branch:*) or Bash(git checkout:*) (no feature branches are cut)",
            "audit workflow's permissions block does NOT include pull-requests: write (only contents: write + issues: write + id-token: write)",
            "audit workflow has a weekly cron firing Mondays at 10am PT (with local-time gate)",
            "audit workflow uses claude-sonnet-4-6 as the model",
            "audit workflow sets show_full_output: true",
            "audit workflow's prompt covers all 4 manifest checks: missing required fields, missing screenshots, id-vs-dir mismatch, invalid category",
            "audit workflow's prompt instructs Claude to list valid categories explicitly (art, data, entertainment, home, transit, utility, weather)",
            "audit workflow's prompt does NOT reference a rejection log (feedback capture opted out)",
            "audit prompt's wrap-up section is preserved (round/batch/progress summary)",
            "audit workflow's prompt does NOT include bucket-A inline-PR instructions (issues-only mode)",
        ]:
            add(t, False, "audit workflow missing")
    else:
        m = re.search(r"--allowed-tools\s+\"([^\"]+)\"", audit)
        tools = m.group(1) if m else ""

        pr_tools = [w for w in ["gh pr create", "gh pr edit"] if w in tools]
        add(
            "audit workflow's --allowed-tools does NOT include Bash(gh pr create:*) (no PRs are opened)",
            not pr_tools,
            f"found PR tools: {pr_tools}",
        )

        branch_tools = [w for w in ["git branch", "git checkout", "git switch"] if w in tools]
        add(
            "audit workflow's --allowed-tools does NOT include Bash(git branch:*) or Bash(git checkout:*) (no feature branches are cut)",
            not branch_tools,
            f"found branch tools: {branch_tools}",
        )

        # permissions block — `pull-requests: write` should NOT appear in the audit job's permissions block.
        # Strip comment lines so a "# Issues-only loop: no pull-requests: write" comment doesn't trigger.
        audit_no_comments = strip_yaml_comments(audit)
        ok = not re.search(r"pull-requests:\s*write", audit_no_comments)
        add(
            "audit workflow's permissions block does NOT include pull-requests: write (only contents: write + issues: write + id-token: write)",
            ok, "pull-requests:write found" if not ok else "absent",
        )

        # weekly Mon 10am PT — single cron pair, gate on Monday + hour 10
        mon_ok, _ = grep(r"(?i)mon|^\s*-\s*cron:\s*['\"]?\d+\s+\d+\s+\*\s+\*\s+[01]", audit)
        ten_ok, _ = grep(r"(?i)10:|hour.*10", audit)
        add(
            "audit workflow has a weekly cron firing Mondays at 10am PT (with local-time gate)",
            mon_ok and ten_ok,
            f"monday-pattern={mon_ok}, hour-10={ten_ok}",
        )

        ok, ev = grep(r"claude-sonnet-4", audit)
        add("audit workflow uses claude-sonnet-4-6 as the model", ok, ev)

        ok, ev = grep(r"show_full_output:\s*['\"]?true['\"]?", audit)
        add("audit workflow sets show_full_output: true", ok, ev)

        ok, ev = all_grep([r"required field", r"screenshot", r"id.*directory|directory.*id|id.*match", r"category|invalid category"], audit, re.IGNORECASE)
        add(
            "audit workflow's prompt covers all 4 manifest checks: missing required fields, missing screenshots, id-vs-dir mismatch, invalid category",
            ok, ev,
        )

        ok, ev = all_grep([r"\bart\b", r"\bdata\b", r"\bentertainment\b", r"\bhome\b", r"\btransit\b", r"\butility\b", r"\bweather\b"], audit)
        add(
            "audit workflow's prompt instructs Claude to list valid categories explicitly (art, data, entertainment, home, transit, utility, weather)",
            ok, ev,
        )

        has_rej = "rejected-edits.jsonl" in audit or "rejection log" in audit.lower()
        add("audit workflow's prompt does NOT reference a rejection log (feedback capture opted out)", not has_rej, "rejection log referenced" if has_rej else "absent")

        ok, ev = grep(r"(?i)wrap.up|round:|progress", audit)
        add("audit prompt's wrap-up section is preserved (round/batch/progress summary)", ok, ev)

        # No bucket A → no "Create a branch named exactly" / "Apply ONLY the bucket-A fixes" / "Open a … PR" in prompt
        # Strip YAML comments first so explanatory comments don't trigger.
        audit_no_comments = strip_yaml_comments(audit)
        bucket_a_signals = sum(1 for p in [
            r"(?i)bucket\s*a\b",
            r"(?i)Create a branch named",
            r"(?i)Apply ONLY the bucket",
            r"(?i)gh pr create",
        ] if re.search(p, audit_no_comments))
        add(
            "audit workflow's prompt does NOT include bucket-A inline-PR instructions (issues-only mode)",
            bucket_a_signals == 0,
            f"bucket-A signals matched: {bucket_a_signals} (want 0)",
        )

    if not state:
        pass  # handled by file-count assertion above
    else:
        try:
            j = json.loads(state)
            if not (j.get("schema_version") == 1 and j.get("round") == 0):
                # add diagnostic, not a separate assertion
                pass
        except json.JSONDecodeError:
            pass

    return results


# -----------------------------------------------------------------------------
# Dispatcher
# -----------------------------------------------------------------------------

GRADERS = {
    "eval-1-create-tests-audit": grade_eval_1,
    "eval-2-tune-docs-audit": grade_eval_2,
    "eval-3-minimal-audit-only": grade_eval_3,
}


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: grade.py <iteration_dir>")
    iter_dir = Path(sys.argv[1]).resolve()

    for eval_dir in sorted(iter_dir.iterdir()):
        if not eval_dir.is_dir():
            continue
        grader = GRADERS.get(eval_dir.name)
        if grader is None:
            print(f"[skip] no grader for {eval_dir.name}")
            continue
        for variant_dir in sorted(eval_dir.iterdir()):
            if not variant_dir.is_dir():
                continue
            # Look for outputs/ either directly under variant_dir (legacy)
            # or under variant_dir/run-1/ (aggregator-compatible layout).
            for candidate in [variant_dir / "outputs", variant_dir / "run-1" / "outputs"]:
                if candidate.exists():
                    outputs = candidate
                    break
            else:
                print(f"[skip] {variant_dir} — no outputs/")
                continue

            results = grader(outputs)
            total = len(results)
            passed = sum(1 for r in results if r["passed"])
            run_dir = outputs.parent
            grading_path = run_dir / "grading.json"
            grading_path.write_text(json.dumps({
                "eval_id": eval_dir.name,
                "variant": variant_dir.name,
                "summary": {
                    "pass_rate": passed / total if total else 0,
                    "passed": passed,
                    "failed": total - passed,
                    "total": total,
                },
                "expectations": results,
            }, indent=2) + "\n")
            print(f"{eval_dir.name}/{variant_dir.name}: {passed}/{total} passed")


if __name__ == "__main__":
    main()
