# Variable catalogue

Every knob a loop exposes, what it controls, where it lives in the rendered files, and the trade-offs. Use this when **tuning** an existing loop or when **rendering** a new one.

Tokens are written as `{{TOKEN_NAME}}` in templates. The substitution is literal text; no Jinja, no nesting.

## Identity & naming

| Token | Example | Used in | Notes |
| --- | --- | --- | --- |
| `{{NAME}}` | `tests-audit` | filenames, branch prefix, issue label, state file path, concurrency group | kebab-case; must not collide with existing `claude-*.yml` |
| `{{SHORT_NAME}}` | `tests` | triage branch prefix (`<short>/issue-*`) | typically the first segment of `{{NAME}}` |
| `{{DISPLAY_NAME}}` | `Tests Audit` | workflow `name:` field, PR/issue titles | Title Case |
| `{{DESCRIPTION}}` | `Sweep of the Python test suite for flaky tests, slow tests, and missing coverage.` | header comment block | one paragraph |

## Schedule & gating

| Token | Default | Used in | Notes |
| --- | --- | --- | --- |
| `{{CRONS}}` | 4 UTC entries for noon + 4pm PT | `on.schedule` | pairs per intended local window; see [pitfalls.md](pitfalls.md#dst-and-cron) |
| `{{TIME_GATE_WINDOWS}}` | `12:00-13:30` and `16:00-17:30` PT | "Gate on local hour" step bash | upper bound includes 30 min slop for GHA delay |
| `{{COOLDOWN_HOURS}}` | `3` | "Dedup" step's `age_h < N` check | between 2 and 4 is sensible for ≤twice-daily |
| `{{DRAFT_CAP}}` | `5` | "Dedup" step's `draft_count -ge N` check | raise for high-volume domains, lower for slow reviewer queues |
| `{{TIMEZONE}}` | `America/Los_Angeles` | gate step's `TZ=` | change for non-US-PT teams |

## Effort scaling

The audit's batch size and issue cap scale **inversely** with the open issue queue. Higher queue → lower batch/cap. Three modes:

| Token | Default | Notes |
| --- | --- | --- |
| `{{EFFORT_HOT_THRESHOLD}}` | `80` | open issues above this → conservative |
| `{{EFFORT_BALANCED_THRESHOLD}}` | `40` | open issues above this → balanced |
| `{{BATCH_CONSERVATIVE}}` | `12` | files audited per run when queue is hot |
| `{{BATCH_BALANCED}}` | `24` | files audited per run when queue is warm |
| `{{BATCH_THOROUGH}}` | `32` | files audited per run when queue is drained |
| `{{CAP_CONSERVATIVE}}` | `32` | max issues filed per run when queue is hot |
| `{{CAP_BALANCED}}` | `60` | max issues filed per run when queue is warm |
| `{{CAP_THOROUGH}}` | `100` | max issues filed per run when queue is drained |

The three caps thread into the prompt via `${{ steps.effort.outputs.cap }}` interpolation.

## Files & paths

| Token | Example | Used in | Notes |
| --- | --- | --- | --- |
| `{{STATE_FILE}}` | `.github/tests-audit-state.json` | state file path, prompt | always `.github/{{NAME}}-state.json` by convention |
| `{{REJECTION_LOG}}` | `.github/tests-audit/rejected-edits.jsonl` | feedback workflow, prompt | always `.github/{{NAME}}/rejected-edits.jsonl` |
| `{{FEEDBACK_DIR}}` | `.github/tests-audit/` | feedback README, `build_rejection.py` | folder for the rejection log and its docs |
| `{{FILE_GLOB_INCLUDES}}` | `tests/**/*.py`, `plugins/*/tests/**/*.py` | prompt's "Glob the repo" section | domain-specific |
| `{{FILE_GLOB_EXCLUDES}}` | `node_modules/`, `.git/`, `**/__pycache__/`, `tools/`, `.claude/` | prompt's glob exclusions | always exclude `.claude/` and `node_modules` |
| `{{EDITABLE_FILE_TYPES}}` | `*.md` or `tests/**/*.py` | "Hard rules" section of prompt | hard ceiling on what Claude is allowed to edit |

## Branch & label conventions

| Token | Example | Used in | Notes |
| --- | --- | --- | --- |
| `{{BRANCH_PREFIX_AUDIT}}` | `tests-audit/` | audit prompt, feedback `if:` condition | inline PRs from the cron use `<prefix>round-<n>-run-<id>` |
| `{{BRANCH_PREFIX_TRIAGE}}` | `tests/issue-` | triage prompt, feedback `if:` condition | per-issue PRs from the triage worker |
| `{{ISSUE_LABEL_DOMAIN}}` | `tests` | issue creation, dedup | broad domain tag, e.g., `docs`, `tests`, `perf` |
| `{{ISSUE_LABEL_AUDIT}}` | `tests-audit` | issue creation, dedup, triage `if:` gate | same as `{{NAME}}`; flags the issue as audit-filed |
| `{{TRIAGE_LABEL}}` | `claude-fix` | issue post-create label application | shared across all loops |

## Model tiers

| Token | Default | Used in | Notes |
| --- | --- | --- | --- |
| `{{MODEL_AUDIT}}` | `claude-sonnet-4-6` | audit `claude_args.--model` | Sonnet handles audits in volume; Opus only if findings are deeply analytical |
| `{{MODEL_REVIEW}}` | `claude-sonnet-4-6` | review `claude_args.--model` | Sonnet is fine for reviews; Haiku is too brief |
| `{{MODEL_TRIAGE_DOCS}}` | `claude-sonnet-4-6` | triage tier-step output (docs branch) | docs-flavored issues |
| `{{MODEL_TRIAGE_CODE}}` | `claude-opus-4-7` | triage tier-step output (default branch) | code/infra issues benefit from Opus |
| `{{MAX_TURNS_AUDIT}}` | `250` | audit `claude_args.--max-turns` | high ceiling; `timeout-minutes` is the real cost backstop |
| `{{MAX_TURNS_TRIAGE}}` | `80` | triage `claude_args.--max-turns` | enough to investigate + write tests + open PR |
| `{{MAX_TURNS_REVIEW}}` | `40` | review `claude_args.--max-turns` | a review run shouldn't need more |

## Tool allowlists

The action's agent-mode default is read-only. Every Edit/Write/git push/gh action must be allowlisted. **Match every Bash pattern the prompt invokes** — see [pitfalls.md](pitfalls.md#-allowed-tools-allowlist--read-only-by-default).

| Token | Used in | Notes |
| --- | --- | --- |
| `{{ALLOWED_TOOLS_AUDIT}}` | audit `claude_args.--allowed-tools` | Read/Glob/Grep/Edit/Write + git + gh issue create + gh pr create + gh label create + jq/date/cat/ls/find |
| `{{ALLOWED_TOOLS_TRIAGE}}` | triage `claude_args.--allowed-tools` | broader than audit — adds `find`, `grep`, `rg`, `python3`, `node`, `npm` for codebase navigation |
| `{{ALLOWED_TOOLS_REVIEW}}` | review `claude_args.--allowed-tools` | read-only — no Edit/Write/git push/gh pr create |

## Prompt body — domain-specific

This is the only token that requires bespoke composition. The rest are mechanical substitutions; this one is the audit's *thinking*.

| Token | Used in | What goes here |
| --- | --- | --- |
| `{{DOMAIN_INTRO}}` | first line of prompt | `"You are the FiestaBoard <domain> auditor. You run unattended <cadence> and audit a batch of <thing>."` |
| `{{BUCKET_A_DEFINITION}}` | "Categorize findings" section | what counts as a trivial mechanical fix in this domain (single-token edit, no ambiguity) |
| `{{BUCKET_B_DEFINITION}}` | "Categorize findings" section | what counts as a missing-thing-to-document/fix issue |
| `{{BUCKET_C_DEFINITION}}` | "Categorize findings" section | what counts as a clarity/quality finding |
| `{{ISSUE_TITLE_TEMPLATE}}` | "For each bucket B or C finding" | e.g., `"tests: <verb> <file> — <one-line summary>"` |
| `{{HARD_RULES_FILE_RESTRICTION}}` | "Hard rules" section | exact glob of files Claude may edit |

When composing these, the prompt's structural skeleton (sweep state, dedup, output format, hard rules, wrap-up) stays unchanged — only the domain-flavored paragraphs change.

## Concurrency

| Token | Example | Notes |
| --- | --- | --- |
| `{{CONCURRENCY_GROUP_AUDIT}}` | `tests-audit` | single global group; not keyed by anything |
| `{{CONCURRENCY_GROUP_FEEDBACK}}` | `tests-audit-feedback` | serialize JSONL log writes |
| `{{CONCURRENCY_GROUP_REVIEW}}` | `claude-tests-audit-review-${{ github.event.pull_request.number }}` | per-PR, with `cancel-in-progress: true` so a new push cancels the prior review |
| `{{CONCURRENCY_GROUP_TRIAGE}}` | `claude-issue-triage-${{ github.event.issue.number }}` | per-issue, with `cancel-in-progress: true` |

## Review workflow path filter

The auto-review workflow is gated on file paths so it doesn't fire for unrelated PRs.

| Token | Example | Used in |
| --- | --- | --- |
| `{{REVIEW_PATHS}}` | `'**.md', 'plugins/*/docs/**', 'docs/**'` (docs case) or `'tests/**/*.py', 'plugins/*/tests/**'` (tests case) | review workflow's `on.pull_request_target.paths` |

## Tuning quick-reference

When the user asks to change …

| Request | Token(s) to change | File(s) |
| --- | --- | --- |
| "Run every 4 hours" | `{{CRONS}}`, `{{TIME_GATE_WINDOWS}}`, `{{COOLDOWN_HOURS}}` | audit workflow |
| "Use Opus" | `{{MODEL_AUDIT}}` | audit workflow |
| "Bump batch size" | `{{BATCH_THOROUGH}}` (and possibly `_BALANCED` / `_CONSERVATIVE`) | audit workflow |
| "Bump issue cap" | `{{CAP_THOROUGH}}` (and others) | audit workflow |
| "Hold off when 3 drafts open" | `{{DRAFT_CAP}}` | audit workflow |
| "Add a Bash command Claude can run" | `{{ALLOWED_TOOLS_AUDIT}}` (or triage / review) | the relevant workflow |
| "Skip files under X" | `{{FILE_GLOB_EXCLUDES}}` | audit workflow's prompt |
| "Auto-review more file types" | `{{REVIEW_PATHS}}` | review workflow |
| "Triage code issues with Sonnet" | `{{MODEL_TRIAGE_CODE}}` | triage workflow |
| "Stop the loop temporarily" | (no token — `gh workflow disable claude-<name>.yml`) | — |

## Cross-references

Some tokens live in multiple places. When tuning, update all of them.

- `{{NAME}}` — audit filename, audit `concurrency.group`, audit prompt's `<name>`, feedback workflow filename, feedback `concurrency.group`, review workflow filename, state file path, rejection log path, feedback dir.
- `{{BRANCH_PREFIX_AUDIT}}` — audit prompt's "Create a branch named …", feedback `if:` `startsWith(...)`, feedback README.
- `{{BRANCH_PREFIX_TRIAGE}}` — triage prompt's "branch <triage-prefix>-<N>-…", feedback `if:` `startsWith(...)`, feedback README.
- `{{ISSUE_LABEL_AUDIT}}` — audit prompt's `gh issue create --label`, audit prompt's `gh issue list --label` (dedup), triage workflow's `if:` `github.event.label.name ==`, triage workflow's `Choose model tier` step's grep.
- `{{MODEL_AUDIT}}` — audit's `claude_args.--model`, audit's `env.AUDIT_MODEL` (if you add visibility), header comment.
