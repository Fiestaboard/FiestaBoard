# Plugin configuration projection implementation plan

Goal: consistently project plugin settings using manifest secret annotations and preserve stored values on masked round-trips.

Architecture: extend the existing recursive configuration helpers with optional schemas and retain legacy name protection. Resolve base IDs for named instances; consult only the existing registry from ConfigManager to avoid initialization cycles. Missing schemas yield empty public configuration. Service operations use their injected registry. Jev selected this approach (probability 0.97, confidence 0.96) over disk manifest reads and output-helper reuse.

Constraints: isolated task worktree; fake credentials; Docker tests; public low-detail alpha PR only; tested main cherry-pick branch; no merges, advisories, comments or publishing.

1. Convert the existing PoC assertions to non-disclosure regression assertions. Run red before production changes.
2. Add focused tests for recursive schema annotations, named instances, missing schemas/startup, stored-only restoration, array identity/reorder/ambiguity and unresolved placeholders. Verify red.
3. Extend mask/unmask helpers and route every plugin projection (REST, MCP, full-config and all-plugin config) through the schema-aware projection. Reject unresolved secret sentinels before saving or applying live configuration.
4. Run regression and existing config/plugin/MCP suites, full Python suite, lint and format. UI gates do not apply: no UI changes.
5. Review diff, add patch changeset and developer documentation, commit/push normally, open low-detail alpha PR, observe CI. Cherry-pick into a fresh main worktree and test without opening a PR. Record exact outcomes in program status and worktree ownership.

Review focus: no registry bootstrap during masking; missing schema fails closed; nested secret fields excluded from array signatures; schema-secret identity fields cannot identify an element; environment-only credentials never persisted.
