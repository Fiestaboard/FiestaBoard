# AI + MCP Test Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a five-layer test harness that permanently catches the class of silent AI/MCP breakage behind #1560 and #1561, then fix every bug it finds.

**Architecture:** Five independent layers, each owning one bug class. Layer 1 parses source across the Python/TypeScript boundary and fails on contract drift. Layer 2 emulates each LLM provider's real request validation. Layer 3 drives MCP over real JSON-RPC transport against real services and asserts on re-read state. Layers 4–5 extend the existing `ai-mcp-e2e-tests` Playwright job. Each layer lands as its own PR.

**Tech Stack:** pytest, Python `ast`, Pydantic, FastAPI `TestClient`, `mcp` (FastMCP), Playwright, stdlib `http.server` (mock-llm).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-11-ai-mcp-test-harness-design.md`
- Commit trailer is exactly `Co-Authored-By: Claude <noreply@anthropic.com>` — no model name or version (CLAUDE.md).
- Never run the API server or `npm run dev` on the host. Python tests run in the dev container: `docker compose -f docker-compose.dev.yml exec fiestaboard pytest`.
- Every analyzer carries meta-tests: one proving it fails on known-bad input, one enforcing a floor on symbols resolved. An analyzer that silently checks nothing is the bug being fixed, re-introduced.
- Every Layer 2 emulator carries a test asserting it *rejects* what it should reject.
- Layer 3 assertions are on re-read state, never on call records.
- Test quality bar (CLAUDE.md): write the test first, watch it fail for the expected reason, put the observed failure output in the PR description.
- No temporary markdown in the repo root.

## Source-of-truth inventory (verified 2026-08-11)

| Thing | Location | Count |
|---|---|---|
| Chat ops (Python) | `src/ai/chat_ops.py:497` `_OP_REGISTRY` | 19 |
| Chat ops (TS) | `web/src/lib/ai-chat-types.ts:163` `ToolCall` union | 19 |
| MCP tools | `src/mcp_server.py` `@mcp.tool()` | 28 |
| MCP prompts | `src/mcp_server.py` `@mcp.prompt()` | 5 |
| MCP resources | `src/mcp_server.py` `@mcp.resource()` | 6 |
| Protocols | `src/ai/protocols.py:225` `PROTOCOLS` | 2 |

## File Structure

**Layer 1 — analyzers (pytest, no container)**
- Create `tests/test_ai_op_contract.py` — chat-op registry ↔ TS union ↔ web switches
- Create `tests/test_mcp_skill_quality.py` — tool/prompt/resource description + schema quality

**Layer 2 — provider conformance (pytest, hermetic)**
- Create `tests/ai/provider_emulators.py` — the emulator library (importable by tests *and* mock-llm)
- Create `tests/ai/test_provider_conformance.py` — every outbound body × every emulator
- Modify `integration-tests/mock-llm/server.py` — provider personality mode

**Layer 3 — MCP over real transport (pytest)**
- Create `tests/test_mcp_state_effects.py` — read → mutate → re-read, no service mocks

**Layer 4 — browser apply-loop (Playwright)**
- Modify `integration-tests/mock-llm/server.py` — `script` scenario
- Modify `web/tests/ai.spec.ts` — both surfaces apply every op

**Layer 5 — skill scenarios (Playwright)**
- Modify `web/tests/mcp.spec.ts` — lifecycle, all prompts, all resources, chains

---

### Task 1: Chat-op contract analyzer (Layer 1)

**Files:**
- Create: `tests/test_ai_op_contract.py`

**Interfaces:**
- Consumes: `src.ai.chat_ops._OP_REGISTRY`, `src.ai.chat_ops.supported_ops()`
- Produces: `_ts_union_ops(path) -> set[str]`, `_switch_case_ops(path, func_name) -> set[str]`

- [ ] **Step 1: Write the failing test**

Three assertions: Python registry == TS union; every op in the TS union is
handled by `labelFor` in `ai-chat-panel.tsx`; same for the drawer's
`labelFor`. Plus meta-tests.

```python
def test_python_registry_matches_ts_union():
    py = set(_OP_REGISTRY)
    ts = _ts_union_ops(WEB / "src/lib/ai-chat-types.ts")
    assert py == ts, f"drift: py-only={py - ts}, ts-only={ts - py}"


def test_editor_chat_panel_labels_every_op():
    ts = _ts_union_ops(WEB / "src/lib/ai-chat-types.ts")
    handled = _switch_case_ops(WEB / "src/components/ai-chat-panel.tsx", "labelFor")
    assert ts <= handled, f"labelFor() returns undefined for: {sorted(ts - handled)}"


def test_analyzer_rejects_known_bad_input(tmp_path):
    f = tmp_path / "x.ts"
    f.write_text('function labelFor(c: ToolCall): string {\n switch (c.op) {\n case "a": return "A";\n }\n}')
    assert _switch_case_ops(f, "labelFor") == {"a"}


def test_analyzer_floor():
    assert len(_ts_union_ops(WEB / "src/lib/ai-chat-types.ts")) >= 19
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec fiestaboard pytest tests/test_ai_op_contract.py -v`
Expected: `test_editor_chat_panel_labels_every_op` FAILS listing
`disable_plugin, enable_plugin, navigate_to_schedule, uninstall_plugin`.
The other three PASS. If the meta-tests fail, the analyzer is broken, not the code.

- [ ] **Step 3: Implement the analyzer helpers**

Regex-based TS parsing (no TS parser available in the Python container):
`_ts_union_ops` matches `op: "<name>"` inside the `ToolCall` union block;
`_switch_case_ops` matches `case "<name>"` inside the named function's body,
found by brace-matching from the function signature.

- [ ] **Step 4: Run to verify the analyzer works and the finding stands**

Expected: 3 pass, 1 fails with the four op names. That failure is finding #2.

- [ ] **Step 5: Fix `labelFor` and re-run**

Add the four missing cases to `ai-chat-panel.tsx`.
Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_ai_op_contract.py web/src/components/ai-chat-panel.tsx
git commit -m "test(ai): assert chat-op contract across Python and TS

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: MCP skill-quality analyzer (Layer 1)

**Files:**
- Create: `tests/test_mcp_skill_quality.py`

**Interfaces:**
- Consumes: `src.mcp_server._build_mcp_server()`, its `_tool_manager`, `_prompt_manager`, `_resource_manager`
- Produces: nothing consumed by later tasks

- [ ] **Step 1: Write the failing test**

```python
def test_every_tool_has_a_description(mcp):
    bad = [n for n, t in mcp._tool_manager._tools.items() if not (t.description or "").strip()]
    assert not bad


def test_every_tool_parameter_is_described(mcp):
    bad = []
    for name, tool in mcp._tool_manager._tools.items():
        props = (tool.parameters or {}).get("properties", {})
        for p, schema in props.items():
            if not schema.get("description", "").strip():
                bad.append(f"{name}.{p}")
    assert not bad


def test_prompts_reference_only_tools_that_exist(mcp):
    tools = set(mcp._tool_manager._tools)
    # Prompt text names tools like `list_pages()`. Every such name must resolve.
    ...


def test_floor_on_surface_size(mcp):
    assert len(mcp._tool_manager._tools) >= 28
```

- [ ] **Step 2: Run to see which assertions fail**

Run: `... pytest tests/test_mcp_skill_quality.py -v`
Expected: unknown until run. Record every failure as a finding.

- [ ] **Step 3: Fix descriptions/schemas the analyzer flags**

- [ ] **Step 4: Re-run — all PASS**

- [ ] **Step 5: Commit**

---

### Task 3: Provider emulator library (Layer 2)

**Files:**
- Create: `tests/ai/provider_emulators.py`

**Interfaces:**
- Produces: `ProviderEmulator` (abstract: `name`, `validate(body, headers) -> None`, raises `ProviderRejection`), and concrete `OpenAIEmulator`, `OpenRouterEmulator`, `LMStudioEmulator`, `OllamaEmulator`, `VLLMEmulator`, `AnthropicEmulator`; `ALL_EMULATORS: list[ProviderEmulator]`; `ProviderRejection(status, message)`.

- [ ] **Step 1: Write the failing test for the emulator itself**

An emulator that accepts everything is the bug being fixed. Prove each says no.

```python
def test_lmstudio_rejects_json_object():
    with pytest.raises(ProviderRejection) as exc:
        LMStudioEmulator().validate(
            {"model": "m", "messages": [], "response_format": {"type": "json_object"}}, {}
        )
    assert exc.value.status == 400
    assert "json_schema" in exc.value.message


def test_lmstudio_accepts_text():
    LMStudioEmulator().validate(
        {"model": "m", "messages": [], "response_format": {"type": "text"}}, {}
    )


def test_anthropic_requires_version_header():
    with pytest.raises(ProviderRejection):
        AnthropicEmulator().validate({"model": "m", "messages": [], "max_tokens": 1}, {})
```

- [ ] **Step 2: Run to verify it fails** — `ImportError`, module does not exist.

- [ ] **Step 3: Implement the emulators**

`LMStudioEmulator.validate` rejects `response_format.type not in {"json_schema","text"}`
with the exact message from #1560. `AnthropicEmulator` requires `x-api-key` +
`anthropic-version`, rejects `response_format`, requires `max_tokens`.

- [ ] **Step 4: Run — all PASS**

- [ ] **Step 5: Commit**

---

### Task 4: Provider conformance matrix (Layer 2)

**Files:**
- Create: `tests/ai/test_provider_conformance.py`

**Interfaces:**
- Consumes: `ALL_EMULATORS` from Task 3; `src.ai.protocols.PROTOCOLS`; the chat body builder in `src/ai/chat.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("emulator", OPENAI_FAMILY_EMULATORS, ids=lambda e: e.name)
def test_generator_body_accepted_by_every_openai_compatible_provider(emulator):
    proto = PROTOCOLS["openai"]
    body = proto.build_body("m", [{"role": "user", "content": "hi"}], 0.7, 1000)
    headers = proto.build_headers("k", {})
    emulator.validate(body, headers)   # raises ProviderRejection on drift
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAILS for `lmstudio` with
`'response_format.type' must be 'json_schema' or 'text'`. This is #1560,
reproduced as a test. Other emulators pass.

- [ ] **Step 3: Do NOT fix yet — commit the failing test as `xfail` with the issue ref**

The fix ships as its own PR per the spec. Mark
`@pytest.mark.xfail(reason="#1560", strict=True)` so the suite stays green and
flips loudly when fixed.

- [ ] **Step 4: Commit the harness**

- [ ] **Step 5: In a separate branch/PR — fix #1560**

Change `src/ai/protocols.py:72` to `{"type": "text"}`, remove the `xfail`,
add a test asserting the generator still recovers JSON from prose via
`_extract_json_object`. Reference the reporter's analysis in the PR.

---

### Task 5: mock-llm provider personalities (Layer 2)

**Files:**
- Modify: `integration-tests/mock-llm/server.py`

- [ ] **Step 1: Add `POST /mock/provider {"provider": "lmstudio"}`**

Default `"permissive"` preserves today's behavior so existing `ai.spec.ts`
tests do not change meaning. When set, every `/v1/chat/completions` body is
run through that provider's validator first and rejected with its real status
and error shape.

- [ ] **Step 2: Add an E2E test in `ai.spec.ts` proving generation succeeds against `lmstudio`**

- [ ] **Step 3: Run, commit**

---

### Task 6: MCP state-effect suite (Layer 3)

**Files:**
- Create: `tests/test_mcp_state_effects.py`

**Interfaces:**
- Consumes: `src.mcp_server._build_mcp_server()`; real `ConfigManager`/`PageService`/`ScheduleService`/`CollectionService` on a `tmp_path` config

- [ ] **Step 1: Write the failing test for one mutating tool**

No mocks. Assert on re-read, not on a call record.

```python
async def test_create_page_actually_persists(real_services):
    before = _call(mcp, "list_pages")["pages"]
    _call(mcp, "create_page", name="Harness", device_type="flagship",
          template=["HELLO", "", "", "", "", ""])
    after = _call(mcp, "list_pages")["pages"]
    assert len(after) == len(before) + 1
    assert any(p["name"] == "Harness" for p in after)
```

- [ ] **Step 2: Run — expect PASS or a real finding**

- [ ] **Step 3: Extend to all 28 tools**

Table-driven: each entry names the tool, its args, and a `verify(services)`
callable that re-reads state. Read-only tools assert shape; mutating tools
assert change. Include `set_active_page` and `set_schedule_mode` — the #1561
pair — as explicit regression cases.

- [ ] **Step 4: Add the floor meta-test**

```python
def test_every_tool_is_covered(mcp):
    assert set(mcp._tool_manager._tools) <= set(COVERED_TOOLS)
```

This is what makes the suite non-vacuous: a new tool added later fails this
until someone writes its state-effect case.

- [ ] **Step 5: Triage findings, commit harness**

---

### Task 7: mock-llm `script` scenario + browser apply-loop (Layer 4)

**Files:**
- Modify: `integration-tests/mock-llm/server.py`
- Modify: `web/tests/ai.spec.ts`

- [ ] **Step 1: Add `POST /mock/script {"ops": [...]}`**

Next completion returns prose plus a `fiestaboard` fenced block per op,
verbatim, so a test picks exactly which op the model "emits".

- [ ] **Step 2: Write a Playwright test per op, per surface**

Both `editor` (`ai-chat-panel`) and `global` (`global-ai-chat-drawer`) — they
have different handler sets, which is how the `labelFor` gap arose. Assert the
page/schedule/collection actually mutated, not that a card rendered.

- [ ] **Step 3: Run against the container, triage, commit**

---

### Task 8: Skill scenarios (Layer 5)

**Files:**
- Modify: `web/tests/mcp.spec.ts`

- [ ] **Step 1: Lifecycle** — `initialize` → `tools/list` → `prompts/list` → `resources/list`, asserting counts ≥ 28/5/6.

- [ ] **Step 2: Execute all 5 prompts** via `prompts/get`, assert each returns non-empty messages and names only tools that exist.

- [ ] **Step 3: Fetch all 6 resources** via `resources/read`, assert each returns parseable content of its declared mime type. Include `fiestaboard://page/{page_id}/preview.html` with a real page id created in the test.

- [ ] **Step 4: Two multi-tool chains**, asserting final state:
  - create page → create schedule referencing it → `set_active_page` → verify board state
  - install plugin → configure → create page using its variable → render preview

- [ ] **Step 5: Raise the CI job timeout if needed; triage; commit**

---

## Self-Review

**Spec coverage:** Layer 1 → Tasks 1–2. Layer 2 → Tasks 3–5. Layer 3 → Task 6. Layer 4 → Task 7. Layer 5 → Task 8. Known work items (#1560, `labelFor`) → Tasks 4 and 1 respectively. CI integration → Tasks 5, 7, 8 extend existing jobs; Tasks 1–3, 6 join `test-platform`. Non-goal "no real providers" honored — all emulated. Non-goal "no model eval" honored — Task 2 covers only the static subset.

**Placeholders:** Task 2 Step 3 and Task 6 Step 5 depend on findings not yet known, which is inherent to a bug hunt; both name the exact command that produces the list. Task 2's `test_prompts_reference_only_tools_that_exist` body is elided — implement by extracting `` `name()` `` and `name(` tokens from prompt text and intersecting with the tool registry.

**Type consistency:** `ProviderRejection(status, message)` used identically in Tasks 3 and 4. `_ts_union_ops` / `_switch_case_ops` signatures match between Task 1 Steps 1 and 3. `_OP_REGISTRY` referenced consistently.
