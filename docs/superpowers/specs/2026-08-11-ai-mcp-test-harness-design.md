# AI + MCP Test Harness — Design

**Date:** 2026-08-11
**Status:** Approved, pending implementation
**Tracking issue:** #1560 (one of the bugs this harness is built to catch)

## Problem

FiestaBoard's AI and MCP features have accumulated silent breakage. Two
defects found in the last 48 hours establish the pattern:

- **#1561** — `set_active_page` and `set_schedule_mode` called
  `ConfigManager` / `ScheduleService` methods that *have never existed*.
  Both tools were complete no-ops in every release shipped. `set_schedule_mode`
  was never even reported by a user; it was found by a wiring analyzer.
  The existing test passed because `MagicMock()` conjures any attribute on
  access, so it asserted that production code called a method that does
  not exist — and agreed with it.
- **#1560** — `_openai_body()` unconditionally sends
  `response_format: {"type": "json_object"}`. LM Studio validates that field
  and returns HTTP 400. Every AI page generation fails against an LM Studio
  provider. The mock LLM in `integration-tests/mock-llm/server.py` accepts
  any body, so no test noticed.

Both are the same failure of method: **the tests assert against a stand-in
that agrees with the code, instead of against something that can say no.**

The features are also under-covered in absolute terms. `mcp.spec.ts` has 5
tests and exercises 1 of 28 tools. The 5 MCP prompts and 6 MCP resources have
zero coverage of any kind.

## Goals

1. Build test infrastructure that catches this class of rot permanently, in CI.
2. Run it, triage what it finds, and fix the bugs it surfaces.
3. Be able to state, with evidence, that FiestaBoard's MCP skills work.

## Non-goals

- Calling real LLM providers. The matrix is emulated; hermetic and free.
- Putting a real model in the loop to test tool *selection*. See
  "Known limits" — this is an eval, not a test, and is explicitly deferred.
- Refactoring `chat.py` or `mcp_server.py` beyond what a specific fix requires.
- Any endpoint outside the AI and MCP surfaces.

## The bug model

Every known and suspected defect falls into one of five classes. The harness
gets one layer per class, so a finding always maps to the layer that owns it.

| Class | Description | Evidence | Why existing tests miss it |
|---|---|---|---|
| **A** | Wiring drift — calling a method that moved or never existed | #1561 | `MagicMock()` conjures the method |
| **B** | Provider-compat drift — request body a real provider rejects | #1560 | mock-llm accepts any body |
| **C** | Contract drift — an op handled on one surface, unhandled on another | `labelFor` (confirmed, below) | no cross-language exhaustiveness check |
| **D** | Semantic no-op — call returns success, state unchanged | #1561 `set_schedule_mode` | assertions on mocks, never on state |
| **E** | Shape drift — flagship assumptions surviving the W×H Note Arrays refactor (#1185) | suspected | AI tests hardcode `flagship` |

### Class C, confirmed before implementation

`web/src/components/ai-chat-panel.tsx:734` — `labelFor(call): string` is a
`switch` over `call.op` with no `default`. The `ToolCall` union
(`web/src/lib/ai-chat-types.ts:163`) declares 19 ops; `labelFor` handles 15.
Missing: `navigate_to_schedule`, `enable_plugin`, `disable_plugin`,
`uninstall_plugin` — all emittable by the backend. Those four return
`undefined` from a function typed `string`.

The same four are present in `global-ai-chat-drawer.tsx`, so the drawer
surface handles them and the editor panel does not.

## Architecture — five layers

### Layer 1 — Contract analyzers

**Where:** `tests/` (pytest). No container. Milliseconds.
**Catches:** C, plus the static half of MCP skill quality.

Extends the source-parsing approach already proven in
`tests/test_service_wiring.py`. Each analyzer resolves names across
language boundaries and fails on drift:

- `src/ai/chat_ops.py` op registry ↔ `web/src/lib/ai-chat-types.ts` `ToolCall`
  union ↔ every consuming `switch` in the web client. This is the analyzer
  that catches `labelFor`.
- The tool list `src/ai/prompt_builder.py` advertises to the model ↔ ops with
  real handlers. A tool the prompt sells but nothing implements means the
  model emits it and nothing happens.
- MCP tools that delegate to REST handlers ↔ those handlers' real signatures.
- **MCP skill quality (static):** every tool has a non-empty description;
  every parameter is typed and described; every prompt references only tools
  that exist in the live registry; no prompt cites board dimensions
  contradicted by the device it targets.

Every analyzer carries meta-tests proving it fails on a known-bad input and
enforcing a floor on resolved-symbol count, so it fails loudly rather than
passing on zero checks. This mirrors what `test_service_wiring.py` does and
is non-negotiable: an analyzer that silently checks nothing is worse than no
analyzer.

### Layer 2 — Provider conformance matrix

**Where:** `tests/ai/` (pytest). Hermetic.
**Catches:** B.

A `ProviderEmulator` per provider family, each encoding that provider's
*actual* request validation, sourced from provider docs and bug reports:

| Emulator | Key validation encoded |
|---|---|
| OpenAI | accepts `json_object`; `max_tokens` deprecation surface |
| OpenRouter | accepts `json_object` |
| **LM Studio** | **rejects `response_format.type` not in `{json_schema, text}` → 400** |
| Ollama | ignores unknown fields; `/v1` path prefix behavior |
| vLLM | OpenAI-compatible subset |
| Anthropic | `x-api-key`, `anthropic-version` required; `system` top-level; no `response_format` |

Every outbound body FiestaBoard constructs — generator and chat, streaming
and non-streaming — is run through every emulator's validator. #1560 becomes
a one-line failing test against `LMStudioEmulator`.

`integration-tests/mock-llm/server.py` gains a **provider personality** mode
driven by the same validators, so the existing `ai.spec.ts` E2E suite runs
against a mock that refuses requests the way LM Studio refuses them. The mock
stops being permissive.

### Layer 3 — MCP over real transport, against real state

**Where:** `tests/` (pytest) driving the real ASGI app.
**Catches:** A, D.

Real JSON-RPC over streamable HTTP, real services on a tmp config, **no
service mocks**. For each of the 28 tools: read → mutate → **re-read and
assert observable state changed**.

Because nothing is mocked, a phantom method raises instead of being conjured
(closing A) and a tool that returns `{"status": "ok"}` while writing nothing
fails its re-read assertion (closing D). Both #1561 bugs would have been
caught here independently of the wiring analyzer.

### Layer 4 — Browser apply-loop

**Where:** `web/tests/ai.spec.ts` (Playwright), existing `ai-mcp-e2e-tests` CI job.
**Catches:** C at runtime, D in the AI path.

`mock-llm` gains a `script` scenario that emits a caller-chosen op verbatim.
Playwright then drives the real chat panel on **both** surfaces (`editor` and
`global` — they have different handler sets, per the `labelFor` finding) and
asserts the page, schedule, or collection actually mutated.

### Layer 5 — Skill scenarios

**Where:** `web/tests/mcp.spec.ts` (extends the existing 5 tests).
**Catches:** the gap between "each tool is correct" and "skills work."

- **Protocol lifecycle:** `initialize` → `tools/list` → `prompts/list` →
  `resources/list`, plus session handling.
- **All 5 prompts executed and validated:** `setup_fiestaboard`,
  `create_display_page`, `schedule_my_day`, `build_a_collection`,
  `troubleshoot_display`. These are the skill definitions; they currently
  have zero coverage. A prompt instructing a model to call a renamed tool
  fails silently today.
- **All 6 resources fetched and validated:** `fiestaboard://plugins`,
  `://pages`, `://page/{page_id}/preview.html`, `://variables`,
  `://schedules`, `://collections`.
- **Multi-tool task chains:** the flows the prompts describe, executed
  end-to-end, asserting final board/config state. Individual tool correctness
  does not prove a chain completes — state produced by tool 3 has to be
  shaped correctly for tool 5.

## Known limits

**Tool selection is not covered.** Whether a model chooses the right tool
from its description is probabilistic and requires a real model in the loop.
That is an eval, not a test. Layers 1–5 prove a chain works *when executed
correctly*; they cannot prove Claude will choose to execute it. Layer 1's
static skill-quality checks flag the cases where selection obviously could
not work (missing description, undescribed parameter, prompt citing a
nonexistent tool), which is the deterministic subset of the problem.

A model-in-the-loop eval is scoped as separate follow-up work.

## Execution plan

1. Build layers 1–5, in order. Layers are independent, so each lands as its
   **own PR** — five harness PRs, not one. Ordering is by cost-to-value:
   Layer 1 is nearly free and already has a confirmed finding, Layer 2 has a
   confirmed finding in #1560, Layer 3 covers the surface with the most
   suspected bugs, Layers 4–5 are the expensive container-bound ones.
2. Run each layer as it lands. Triage failures into a ranked findings list,
   each tagged with its bug class and owning layer.
3. Then **one PR per confirmed bug**.
4. Each fix is written test-first against the layer that caught it, per the
   repo's test quality bar: watch the test fail for the right reason before
   writing the fix, and put the observed failure output in the PR description.

A harness layer PR may land with its own findings still red only if the
failing assertions are marked as known-failing with an issue reference;
otherwise the layer PR includes the fix. This keeps `main` green while the
findings list is worked through.

Known work items already identified, to be confirmed by the harness:

- #1560 — `response_format` hardcoded to `json_object` (class B)
- `labelFor` non-exhaustive switch, 4 ops unhandled (class C)

## CI integration

No new top-level job. Layers 1–3 join the existing `test-platform` pytest
run. Layers 4–5 extend the existing `ai-mcp-e2e-tests` job, which already
builds the image, starts `mock-llm` + FiestaBoard containers, probes the MCP
mount, and runs `ai.spec.ts mcp.spec.ts`. The job's 12-minute timeout and
8-minute test timeout may need raising as Layer 5 lands.

## Testing the harness itself

Per the repo's test quality bar, coverage is not proof, and a harness built
to catch rot must itself be proven non-vacuous:

- Every Layer 1 analyzer has a meta-test feeding it known-bad input and
  asserting it fails, plus a floor on symbols resolved.
- Every Layer 2 emulator has a test asserting it *rejects* the bodies it
  should reject — an emulator that accepts everything is the bug we are
  fixing, re-introduced.
- Layer 3 assertions are on re-read state, never on call records.
