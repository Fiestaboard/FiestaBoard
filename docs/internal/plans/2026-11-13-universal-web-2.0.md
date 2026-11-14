# Slice 2.0: adopt FiestaUI alpha.2

1. Preserve the handoff's exact npm pin and changeset; delete the installed-package lock entry and re-resolve it in Docker to avoid stale tarball metadata.
2. Verify a clean registry install, typecheck, lint, formatting, production build, full unit coverage, browser layout regressions, dark/light Storybook accessibility and the Docker ui-builder target. Fix only confirmed compatibility fallout.
3. Commit with the repository trailer, push normally, update PR #2471's body, and record observed local/CI results in the program status and worktree row. Do not merge or approve anything.

This dependency-only update uses existing tests. No new UI flow or primitive is introduced. The exact registry pin and lockfile remedy are prescribed. Under severe shared Docker contention, Jev recommended a container-local copy of the same web sources and root fixtures for sequential verification (`snapshot`, p=0.95). Keep the original interrupted/timeout attempts distinct from completed checks.
