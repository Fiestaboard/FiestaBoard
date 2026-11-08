---
description: Verification evidence and review limits for the combined native client API preparation.
---

# Native client API preparation verification

All identified backend preparation is collected in draft
[PR #2373](https://github.com/Fiestaboard/FiestaBoard/pull/2373). The contract is
[native-client-content.md](native-client-content.md), with authentication in
[native-client-authentication.md](native-client-authentication.md). This is a
backend handoff, not a claim of native application feature parity or deployment.

## Implementation and review

Sol 6.1 implemented the content revisions, rich document preservation, and
AI/MCP integration tracks. Astra independently reviewed document/auth behavior
and the combined content/tool behavior. Both reviews passed after corrections:

- Opaque page shape extensions no longer enter another shape's color validation.
- The actual web AI request carries original page, collection, and schedule
  revision metadata; testing only the prompt formatter missed this boundary.
- Original revisions survive delayed approval and editor snapshots. Service
  ownership and lock order remain stable during restore and default changes.
- Router layering, generated API reference, and older test fixtures were brought
  into agreement with the deliberate additive response metadata.

Independent review included unchanged failing reproductions, real outgoing web
request checks, simultaneous default writers, a tool preparation race, and lock
ordering probes. All actionable findings were resolved. Intentional legacy
writes and explicit demo resets remain documented compatibility operations.

## Regression evidence

| Check | Result |
| --- | --- |
| Offline Python suite, 439 files in 13 bounded groups | 14,448 passed; 3 skipped; 14 integration tests deselected |
| Complete web suite | 260 files; 3,066 passed; 7 skipped |
| Web checks after the final AI context correction | 148 passed, including the actual outgoing request regression |
| Web type checking | Passed |
| Upstream 10.1.4 registry/version merge checks | 298 passed |
| Changed Python lint/format checks | Passed |
| Changed web lint/format checks | Passed |
| Generated API reference check | Passed |

The Python coverage combines the initial immutable source snapshot `46d448323`,
corrected failed-group runs at `2f106574b`, and the final group at `68ea45e25`.
The final group includes the last three explicit default-response expectations.
The web full run used `46d448323`; the subsequent AI context correction
`c0a7d45c7` passed its 148-test focused web run and type checking, with another
eight request-boundary tests independently rerun by Astra. The upstream merge
adds registry/version data only; its focused checks passed separately.

Tests ran in disposable Docker containers. Python used
`fiestaboard-ios-contract:clean`; web dependencies used the exact-lockfile
`fiestaboard-ios-api-node:10.1.2` image (later version-only lock changes did not
change dependencies). Fixture tests used `--network none`, temporary data, and
no hardware mounts. No real board or provider account was contacted.

## Initial failures and corrected harness

The first broad run exposed stale contract mocks, missing generated reference
updates, and a router layering violation. Those were corrected without waivers
or weakened content assertions. Restart/restore tests now compare every content
field, require a new runtime generation, and verify the old token receives 412.

Other initial failures came from the harness: executable shell fixtures on a
temporary filesystem without execution permission, a source archive without
the Git index needed by the tracked-image check, relative-path tests run outside
the repository root, and temporary data accumulating until disk space ran out.
Corrected runs used the repository root, an indexed source copy, an executable
temporary filesystem, and a fresh temporary directory removed after each group.
One existing HTTP contract fixture also needed deterministic DNS instead of a
real lookup; its transport was already mocked. The production URL guard remains
unchanged. Every initially failing group was rerun to green.

## Limits

The 14 tests marked integration were deliberately excluded from the offline
run. Existing deprecation/test-environment warnings remain. This evidence does
not establish live provider sign-in, Home Assistant gateway authentication,
hardware delivery, multiple server-process locking, native visual acceptance,
or App Store readiness. The PR remains draft and unmerged for review.
