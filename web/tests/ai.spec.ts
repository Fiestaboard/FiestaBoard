/**
 * AI E2E tests.
 *
 * Exercises the full FiestaBoard AI stack:
 *
 *   Playwright → Next.js UI / FastAPI /pages/ai/* → mock OpenAI server
 *
 * The mock OpenAI server (integration-tests/mock-llm/server.py) speaks just
 * enough of the chat completions API for src/ai/generator.py to round-trip
 * end-to-end. We configure a provider pointing at it via PUT /settings/ai,
 * then drive both the API and the Settings → Integrations tab UI.
 *
 * Gated behind RUN_AI_TESTS in playwright.config.ts because the spec needs
 * the mock-llm container reachable at MOCK_LLM_URL — only the dedicated CI
 * job (`ai-mcp-e2e-tests`) starts that container.
 *
 * The chat is a server-side agent loop over the in-process MCP server: the
 * "model" here is the mock, scripted per test (`/mock/script` with `steps`
 * for multi-round turns), and every tool it calls runs for real.
 */
import { type APIRequestContext, expect, test } from "@playwright/test";

const BASE_URL = process.env.BASE_URL || "http://localhost:4420";
const API_URL = `${BASE_URL}/api`;
// MOCK_LLM_URL is the URL the FiestaBoard container uses to reach the mock
// LLM (container-network). MOCK_LLM_CONTROL_URL is the URL Playwright (host)
// uses to drive /mock/state, /mock/reset, /mock/scenario. They may differ
// when running in Docker on CI.
const MOCK_LLM_URL = process.env.MOCK_LLM_URL || "http://localhost:9100";
const MOCK_LLM_CONTROL_URL = process.env.MOCK_LLM_CONTROL_URL || MOCK_LLM_URL;

const PROVIDER_ID = "mock-openai";
const PROVIDER_NAME = "Mock OpenAI";
const PROVIDER_MODEL = "mock-model-v1";
const PROVIDER_API_KEY = "sk-mock-test-key-do-not-use";
const MASK = "***";

/**
 * Configure the mock LLM as the only AI provider and enable AI.
 * Idempotent — safe to call from every test.
 */
async function configureMockProvider(request: APIRequestContext): Promise<void> {
  const res = await request.put(`${API_URL}/settings/ai`, {
    data: {
      enabled: true,
      providers: [
        {
          id: PROVIDER_ID,
          name: PROVIDER_NAME,
          protocol: "openai",
          base_url: `${MOCK_LLM_URL}/v1`,
          api_key: PROVIDER_API_KEY,
          models: [PROVIDER_MODEL],
          default_model: PROVIDER_MODEL,
          headers: {},
        },
      ],
      default_provider_id: PROVIDER_ID,
    },
  });
  expect(res.ok()).toBe(true);
}

async function disableAi(request: APIRequestContext): Promise<void> {
  const res = await request.put(`${API_URL}/settings/ai`, {
    data: { enabled: false, providers: [], default_provider_id: null },
  });
  expect(res.ok()).toBe(true);
}

async function setMockScenario(scenario: string): Promise<void> {
  const res = await fetch(`${MOCK_LLM_CONTROL_URL}/mock/scenario`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario }),
  });
  if (!res.ok) {
    throw new Error(`setMockScenario(${scenario}) failed: ${res.status}`);
  }
}

async function resetMock(): Promise<void> {
  const res = await fetch(`${MOCK_LLM_CONTROL_URL}/mock/reset`, { method: "POST" });
  if (!res.ok) throw new Error(`resetMock failed: ${res.status}`);
}

async function getMockState(): Promise<{
  scenario: string;
  request_count: number;
  history: Array<Record<string, unknown>>;
}> {
  const res = await fetch(`${MOCK_LLM_CONTROL_URL}/mock/state`);
  if (!res.ok) throw new Error(`getMockState failed: ${res.status}`);
  return res.json();
}

/**
 * Call POST /pages/ai/generate, retrying once after the 1-second throttle
 * window if we hit a 429. The endpoint rejects calls landing less than
 * _AI_GENERATE_MIN_INTERVAL_SECONDS (1s) after the previous one — tests
 * that run back-to-back trip it without this.
 *
 * The throttle runs after body validation since the conventions pass, so a
 * malformed body answers 422 and is returned straight through rather than
 * retried.
 */
async function callGenerate(
  request: APIRequestContext,
  body: Record<string, unknown>,
): Promise<{ status: number; data: Record<string, unknown> }> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const res = await request.post(`${API_URL}/pages/ai/generate`, { data: body });
    const status = res.status();
    const data = (await res.json()) as Record<string, unknown>;
    if (status === 429 && attempt === 0) {
      await new Promise((r) => setTimeout(r, 1200));
      continue;
    }
    return { status, data };
  }
  throw new Error("callGenerate: retried but still got 429");
}

/**
 * Switch the mock LLM into a provider personality — it then validates
 * request bodies the way that real provider does. Default is "permissive".
 */
async function setMockProvider(provider: string): Promise<void> {
  const res = await fetch(`${MOCK_LLM_CONTROL_URL}/mock/provider`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider }),
  });
  if (!res.ok) throw new Error(`setMockProvider(${provider}) failed: ${res.status}`);
}

/**
 * Stage exactly what the "model" emits on the next chat completion: prose
 * plus one fenced tool block per op. Arms the "script" scenario.
 */
type MockStep = { prose?: string; ops?: Array<Record<string, unknown>> };

/**
 * Stage what the "model" says. A single script is returned for every
 * completion; `steps` hands out one entry per model call, which is how a
 * turn that runs a tool and then replies is driven (the loop calls the
 * model again with the tool result).
 */
async function setMockScript(script: MockStep | { steps: MockStep[] }): Promise<void> {
  const res = await fetch(`${MOCK_LLM_CONTROL_URL}/mock/script`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(script),
  });
  if (!res.ok) throw new Error(`setMockScript failed: ${res.status}`);
}

/** One parsed SSE frame from /pages/ai/chat. */
interface ChatFrame {
  event: string;
  data: Record<string, unknown>;
}

/**
 * POST /pages/ai/chat and parse the SSE stream into frames.
 *
 * Playwright's APIRequestContext buffers the body, which is fine here: the
 * mock closes the stream promptly and we assert on the whole transcript.
 */
async function callChat(request: APIRequestContext, body: Record<string, unknown>): Promise<ChatFrame[]> {
  const res = await request.post(`${API_URL}/pages/ai/chat`, { data: body });
  expect(res.status(), await res.text()).toBe(200);
  const raw = await res.text();

  const frames: ChatFrame[] = [];
  for (const block of raw.split("\n\n")) {
    const eventLine = block.split("\n").find((l) => l.startsWith("event: "));
    const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
    if (!eventLine || !dataLine) continue;
    frames.push({
      event: eventLine.slice("event: ".length).trim(),
      data: JSON.parse(dataLine.slice("data: ".length)),
    });
  }
  return frames;
}

test.describe("AI", () => {
  test.beforeAll(async () => {
    // Sanity: confirm the mock LLM is actually reachable from the test
    // host before we let dozens of tests fail with the same root cause.
    const res = await fetch(`${MOCK_LLM_CONTROL_URL}/mock/state`).catch(() => null);
    test.skip(
      !res || !res.ok,
      `Mock LLM control endpoint unreachable at ${MOCK_LLM_CONTROL_URL}. ` +
        "This spec is gated behind RUN_AI_TESTS and the dedicated CI job — " +
        "starting it manually requires running integration-tests/mock-llm/server.py.",
    );
  });

  test.beforeEach(async () => {
    // resetMock() restores scenario="ok" AND provider="permissive", so a
    // provider-matrix test can't leak strict validation into its neighbours.
    await resetMock();
  });

  test.describe("/pages/ai/context", () => {
    test("returns a debug context payload", async ({ request }) => {
      const res = await request.get(`${API_URL}/pages/ai/context?device_type=flagship`);
      expect(res.ok()).toBe(true);
      const data = await res.json();
      // The exact shape comes from build_prompt(...).to_dict(); we assert on
      // top-level keys that are stable across prompt-builder refactors.
      expect(data).toHaveProperty("system_prompt");
      expect(data).toHaveProperty("user_prompt");
    });

    // 422, not 400: the Phase 2 conventions pass made device_type a typed
    // Literal query parameter, so the rejection is FastAPI's own schema
    // validation rather than a hand-rolled membership check in the handler.
    test("rejects bogus device_type with 422", async ({ request }) => {
      const res = await request.get(`${API_URL}/pages/ai/context?device_type=potato`);
      expect(res.status()).toBe(422);
    });
  });

  test.describe("/settings/ai round-trip + masking", () => {
    test("default settings have AI disabled and no providers", async ({ request }) => {
      // Wipe whatever earlier tests left behind so the assertion is clean.
      await disableAi(request);
      const res = await request.get(`${API_URL}/settings/ai`);
      expect(res.ok()).toBe(true);
      const data = await res.json();
      expect(data.enabled).toBe(false);
      expect(Array.isArray(data.providers)).toBe(true);
    });

    test("PUT persists a provider and masks the api_key on GET", async ({ request }) => {
      await configureMockProvider(request);

      const res = await request.get(`${API_URL}/settings/ai`);
      expect(res.ok()).toBe(true);
      const data = await res.json();
      expect(data.enabled).toBe(true);
      expect(data.default_provider_id).toBe(PROVIDER_ID);

      const provider = data.providers.find((p: { id: string }) => p.id === PROVIDER_ID);
      expect(provider).toBeDefined();
      expect(provider.name).toBe(PROVIDER_NAME);
      // The key MUST come back masked — anything else leaks the secret to
      // every GET caller.
      expect(provider.api_key).toBe(MASK);
      // But the stored model + base_url are not secrets and round-trip raw.
      expect(provider.default_model).toBe(PROVIDER_MODEL);
      expect(provider.base_url).toBe(`${MOCK_LLM_URL}/v1`);
    });

    test("PUT with api_key='***' preserves the stored key", async ({ request }) => {
      await configureMockProvider(request);
      // Send a "draft" that has only the mask in the api_key field — the
      // server should keep the previously-stored key rather than wipe it.
      const update = await request.put(`${API_URL}/settings/ai`, {
        data: {
          enabled: true,
          providers: [
            {
              id: PROVIDER_ID,
              name: PROVIDER_NAME,
              protocol: "openai",
              base_url: `${MOCK_LLM_URL}/v1`,
              api_key: MASK,
              models: [PROVIDER_MODEL],
              default_model: PROVIDER_MODEL,
              headers: {},
            },
          ],
          default_provider_id: PROVIDER_ID,
        },
      });
      expect(update.ok()).toBe(true);

      // Round-trip through /test using the persisted (unmasked) key — if
      // the server lost it the upstream call would 401, since the mock LLM
      // would receive an empty Authorization header.
      const testRes = await request.post(`${API_URL}/settings/ai/test`, {
        data: { provider_id: PROVIDER_ID, model: PROVIDER_MODEL },
      });
      expect(testRes.ok()).toBe(true);
      const testData = await testRes.json();
      expect(testData.ok).toBe(true);

      const state = await getMockState();
      const last = state.history[state.history.length - 1];
      expect(last.headers).toMatchObject({
        authorization: `Bearer ${PROVIDER_API_KEY}`,
      });
    });
  });

  test.describe("/settings/ai/test", () => {
    test("reports ok=true when the provider responds", async ({ request }) => {
      await configureMockProvider(request);
      const res = await request.post(`${API_URL}/settings/ai/test`, {
        data: { provider_id: PROVIDER_ID, model: PROVIDER_MODEL },
      });
      expect(res.ok()).toBe(true);
      const data = await res.json();
      expect(data.ok).toBe(true);
      expect(data.model_used).toBe(PROVIDER_MODEL);
    });

    test("draft provider override works without saving first", async ({ request }) => {
      // Empty out persisted providers, then test a draft that points at
      // the mock — mirrors the unsaved-draft "Test connection" button in
      // the settings UI.
      await disableAi(request);
      const res = await request.post(`${API_URL}/settings/ai/test`, {
        data: {
          provider: {
            id: "draft-only",
            name: "Draft",
            protocol: "openai",
            base_url: `${MOCK_LLM_URL}/v1`,
            api_key: "sk-draft",
            models: [PROVIDER_MODEL],
            default_model: PROVIDER_MODEL,
          },
        },
      });
      expect(res.ok()).toBe(true);
      const data = await res.json();
      expect(data.ok).toBe(true);
    });

    test("reports ok=false when the upstream returns an auth error", async ({ request }) => {
      await configureMockProvider(request);
      await setMockScenario("auth_error");
      const res = await request.post(`${API_URL}/settings/ai/test`, {
        data: { provider_id: PROVIDER_ID, model: PROVIDER_MODEL },
      });
      // The endpoint itself returns 200 — the failure is reported in the body.
      expect(res.ok()).toBe(true);
      const data = await res.json();
      expect(data.ok).toBe(false);
      expect(String(data.message)).toMatch(/invalid api key/i);
    });
  });

  test.describe("/pages/ai/generate", () => {
    test("returns 400 when AI is disabled", async ({ request }) => {
      await disableAi(request);
      const { status, data } = await callGenerate(request, {
        prompt: "draw a clock",
        device_type: "flagship",
      });
      expect(status).toBe(400);
      expect(String(data.detail || "")).toMatch(/not enabled|no .* provider/i);
    });

    // 422, not 400: `prompt` is a required field on the AIGenerateRequest
    // model since the conventions pass, so a missing one never reaches the
    // handler. The 400 below — the generator's own message — is unchanged.
    test("returns 422 when prompt is missing", async ({ request }) => {
      await configureMockProvider(request);
      const { status } = await callGenerate(request, {
        device_type: "flagship",
      });
      expect(status).toBe(422);
    });

    test("happy path round-trips through the mock and returns a valid page", async ({ request }) => {
      await configureMockProvider(request);
      await setMockScenario("ok");

      const { status, data } = await callGenerate(request, {
        prompt: "show hello world",
        device_type: "flagship",
      });
      expect(status).toBe(200);
      expect(data).toHaveProperty("page");
      const page = data.page as Record<string, unknown>;
      expect(page.type).toBe("template");
      expect(page.device_type).toBe("flagship");
      expect(Array.isArray(page.template)).toBe(true);
      expect((page.template as unknown[]).length).toBe(6);
      expect(data.provider_id).toBe(PROVIDER_ID);
      expect(data.model_used).toBe(PROVIDER_MODEL);

      // The mock should have seen exactly the model we asked for, and the
      // user prompt should be in the last message.
      const state = await getMockState();
      expect(state.request_count).toBeGreaterThanOrEqual(1);
      const last = state.history[state.history.length - 1];
      expect(last.model).toBe(PROVIDER_MODEL);
      const messages = last.messages as Array<{ role: string; content: string }>;
      const lastUserMsg = [...messages].reverse().find((m) => m.role === "user");
      expect(lastUserMsg).toBeDefined();
      expect(lastUserMsg!.content).toContain("show hello world");
    });

    test("surfaces upstream auth error as a 400 with the provider message", async ({ request }) => {
      await configureMockProvider(request);
      await setMockScenario("auth_error");
      const { status, data } = await callGenerate(request, {
        prompt: "show hello world",
        device_type: "flagship",
      });
      expect(status).toBe(400);
      expect(String(data.detail || "")).toMatch(/invalid api key|auth/i);
    });

    test("returns 400 when the model emits malformed JSON", async ({ request }) => {
      await configureMockProvider(request);
      await setMockScenario("bad_json");
      const { status, data } = await callGenerate(request, {
        prompt: "give me anything",
        device_type: "flagship",
      });
      expect(status).toBe(400);
      expect(String(data.detail || "")).toMatch(/json|did not contain|valid/i);
    });

    test("returns 400 when the model omits the required template field", async ({ request }) => {
      await configureMockProvider(request);
      await setMockScenario("missing_template");
      const { status, data } = await callGenerate(request, {
        prompt: "give me anything",
        device_type: "flagship",
      });
      expect(status).toBe(400);
      expect(String(data.detail || "")).toMatch(/template/i);
    });
  });

  test.describe("Settings → Integrations UI", () => {
    test("AI Settings card renders inside the Integrations tab", async ({ page, request }) => {
      await configureMockProvider(request);
      // The WizardProvider holds every non-/login page on a full-screen
      // loader (then SetupWizard) while `/config/validate` reports
      // `is_first_run: true`, so the Settings tabs never mount. A fresh
      // CI container has no board configured — PUT a stub so the wizard
      // gets out of the way.
      const boardRes = await request.put(`${API_URL}/config/board`, {
        data: { api_mode: "local", local_api_key: "ai-e2e-stub", host: "127.0.0.1" },
      });
      expect(boardRes.ok()).toBe(true);

      await page.goto("/settings");
      // Settings page splits into tabs (General / Hardware / Behavior /
      // Integrations / System / Advanced). AI Settings live in Integrations.
      await page.getByRole("tab", { name: "Integrations", exact: true }).click();

      // The settings component is loaded — assert on a stable string from
      // its header / description copy rather than a specific button label.
      await expect(page.getByText(/AI Providers|AI Settings|Add provider/i).first()).toBeVisible();
      // The provider we configured via the API should appear in the list.
      await expect(page.getByText(PROVIDER_NAME, { exact: false }).first()).toBeVisible();
    });
  });

  // -------------------------------------------------------------------
  // Provider conformance (Layer 2, end-to-end)
  //
  // tests/ai/test_provider_conformance.py checks the outbound body against
  // emulators in-process. This runs the same idea through the real HTTP
  // path: a mock that refuses requests the way the named provider refuses
  // them. #1560 is the case that matters — LM Studio 400s on
  // response_format json_object, so generation was hard-blocked there.
  // -------------------------------------------------------------------
  test.describe("provider conformance", () => {
    for (const provider of ["openai", "openrouter", "lmstudio", "ollama", "vllm"]) {
      test(`page generation succeeds against ${provider} validation`, async ({ request }) => {
        await configureMockProvider(request);
        await setMockProvider(provider);

        const { status, data } = await callGenerate(request, {
          prompt: `a page, generated against ${provider}`,
          device_type: "flagship",
        });

        expect(status, JSON.stringify(data)).toBe(200);
        expect(data.page).toBeTruthy();
      });
    }

    test("the mock actually rejects what LM Studio rejects", async () => {
      // Without this, every test above could be passing vacuously against a
      // mock that says yes to everything — precisely how #1560 shipped.
      await setMockProvider("lmstudio");
      const res = await fetch(`${MOCK_LLM_CONTROL_URL}/v1/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "mock-model-v1",
          messages: [{ role: "user", content: "hi" }],
          response_format: { type: "json_object" },
        }),
      });
      expect(res.status).toBe(400);
      const body = (await res.json()) as { error: string };
      // LM Studio's envelope is a flat string, not {error:{message}}.
      expect(typeof body.error).toBe("string");
      expect(body.error).toContain("json_schema");
    });

    test("the generator does not ask for json_object mode", async ({ request }) => {
      await configureMockProvider(request);
      await callGenerate(request, { prompt: "check the wire format", device_type: "flagship" });

      const state = await getMockState();
      const last = state.history[state.history.length - 1];
      expect(last, "no request reached the mock").toBeTruthy();
      // Regression pin for #1560 at the wire level.
      expect(last.response_format).toEqual({ type: "text" });
    });
  });

  // -------------------------------------------------------------------
  // Chat streaming + tool-call grammar (Layer 4)
  //
  // /pages/ai/chat had no E2E coverage at all: the mock could not stream,
  // so nothing exercised the SSE path or the fenced-tool-block parser that
  // turns model prose into structured ops.
  // -------------------------------------------------------------------
  test.describe("/pages/ai/chat", () => {
    test("streams prose as text frames and ends with done", async ({ request }) => {
      await configureMockProvider(request);
      await setMockScript({ prose: "Here is what I will do.", ops: [] });

      const frames = await callChat(request, {
        messages: [{ role: "user", content: "hello" }],
        device_type: "flagship",
        surface: "editor",
      });

      const text = frames
        .filter((f) => f.event === "text")
        .map((f) => f.data.delta as string)
        .join("");
      expect(text).toContain("Here is what I will do.");

      const done = frames.find((f) => f.event === "done");
      expect(done, "stream never emitted a done frame").toBeTruthy();
      expect(done!.data.model_used).toBe(PROVIDER_MODEL);
    });

    test("a fenced tool block runs through MCP and comes back as tool_call + tool_result", async ({ request }) => {
      await configureMockProvider(request);
      await setMockScript({
        steps: [
          {
            prose: "Creating that page.",
            ops: [
              {
                op: "create_page",
                args: {
                  name: "Scripted Page",
                  template_lines: ["SCRIPTED", "", "", "", "", ""],
                  device_type: "flagship",
                },
              },
            ],
          },
          { prose: "Done." },
        ],
      });

      const frames = await callChat(request, {
        messages: [{ role: "user", content: "make a page" }],
        device_type: "flagship",
        surface: "global",
      });

      const call = frames.find((f) => f.event === "tool_call");
      expect(call, `no tool_call frame in: ${JSON.stringify(frames)}`).toBeTruthy();
      expect(call!.data.name).toBe("create_page");
      expect(call!.data.requires_approval).toBe(false);
      expect((call!.data.args as Record<string, unknown>).name).toBe("Scripted Page");

      const result = frames.find((f) => f.event === "tool_result");
      expect(result, "the loop never ran the tool").toBeTruthy();
      expect(result!.data.status).toBe("ok");
      const pageId = (result!.data.result as Record<string, unknown>).page_id as string;

      // The page is real, over REST.
      const pages = await (await request.get(`${API_URL}/pages`)).json();
      const list = (Array.isArray(pages) ? pages : pages.pages || []) as Array<Record<string, unknown>>;
      expect(list.some((p) => p.id === pageId && p.name === "Scripted Page")).toBe(true);

      const done = frames.find((f) => f.event === "done");
      expect(done!.data.reason).toBe("complete");
    });

    test("tool blocks are parsed across SSE delta boundaries", async ({ request }) => {
      // The mock chunks content at 24 chars, so a fenced block is split
      // across several deltas. A parser that only handled whole-chunk
      // fences would pass the test above and fail here.
      await configureMockProvider(request);
      await setMockScript({
        steps: [{ prose: "x".repeat(200), ops: [{ op: "list_pages", args: {} }] }, { prose: "ok" }],
      });

      const frames = await callChat(request, {
        messages: [{ role: "user", content: "go" }],
        device_type: "flagship",
        surface: "global",
      });

      expect(frames.filter((f) => f.event === "text").length).toBeGreaterThan(1);
      const call = frames.find((f) => f.event === "tool_call");
      expect(call, "fence split across deltas was not reassembled").toBeTruthy();
      expect(call!.data.name).toBe("list_pages");
      expect(call!.data.read_only).toBe(true);
    });

    test("an unknown op is reported as a warning, not a tool_call", async ({ request }) => {
      await configureMockProvider(request);
      await setMockScript({ ops: [{ op: "definitely_not_a_real_op", args: {} }] });

      const frames = await callChat(request, {
        messages: [{ role: "user", content: "do something odd" }],
        device_type: "flagship",
        surface: "editor",
      });

      expect(frames.find((f) => f.event === "tool_call")).toBeFalsy();
      expect(frames.some((f) => f.event === "warning" || f.event === "error")).toBe(true);
    });

    test("a malformed op is rejected rather than passed through", async ({ request }) => {
      // create_page requires template_lines.
      await configureMockProvider(request);
      await setMockScript({ ops: [{ op: "create_page", args: { name: "" } }] });

      const frames = await callChat(request, {
        messages: [{ role: "user", content: "break it" }],
        device_type: "flagship",
        surface: "editor",
      });

      expect(frames.find((f) => f.event === "tool_call")).toBeFalsy();
      expect(frames.some((f) => f.event === "warning" || f.event === "error")).toBe(true);
    });

    test("a destructive tool pauses for approval and runs only on approve", async ({ request }) => {
      await configureMockProvider(request);
      const pageRes = await request.post(`${API_URL}/pages`, {
        data: {
          name: "Doomed",
          type: "template",
          device_type: "flagship",
          template: ["X", "", "", "", "", ""],
          duration_seconds: 300,
        },
      });
      const pageId = (await pageRes.json()).id as string;

      await setMockScript({ prose: "Deleting it.", ops: [{ op: "delete_page", args: { page_id: pageId } }] });
      const ask = [{ role: "user", content: "delete the doomed page" }];
      const frames = await callChat(request, { messages: ask, device_type: "flagship" });

      const call = frames.find((f) => f.event === "tool_call")!;
      expect(call.data.requires_approval).toBe(true);
      const done = frames.find((f) => f.event === "done")!;
      expect(done.data.reason).toBe("awaiting_approval");
      expect(frames.find((f) => f.event === "tool_result")).toBeFalsy();

      const transcript = [
        ...ask,
        {
          role: "assistant",
          content: "Deleting it.",
          tool_calls: [{ id: call.data.id, name: "delete_page", args: call.data.args }],
        },
      ];
      await setMockScript({ prose: "Gone." });
      const approved = await callChat(request, {
        messages: transcript,
        device_type: "flagship",
        resume: { tool_call_id: call.data.id, decision: "approve" },
      });
      expect(approved.find((f) => f.event === "tool_result")!.data.status).toBe("ok");

      const pages = await (await request.get(`${API_URL}/pages`)).json();
      const list = (Array.isArray(pages) ? pages : pages.pages || []) as Array<Record<string, unknown>>;
      expect(list.some((p) => p.id === pageId)).toBe(false);
    });

    // Both 422 rather than 400 since the conventions pass typed the chat
    // body: `messages` has min_length 1 and `surface` is a Literal, so both
    // rejections are FastAPI's schema validation. What still matters — and
    // is still asserted — is that a rejected request comes back as a JSON
    // error and never as a 200 event-stream the drawer would render as an
    // empty assistant turn.
    test("rejects an empty messages array", async ({ request }) => {
      await configureMockProvider(request);
      const res = await request.post(`${API_URL}/pages/ai/chat`, {
        data: { messages: [], device_type: "flagship" },
      });
      expect(res.status()).toBe(422);
      expect(res.headers()["content-type"]).toContain("application/json");
    });

    test("rejects an invalid surface", async ({ request }) => {
      await configureMockProvider(request);
      const res = await request.post(`${API_URL}/pages/ai/chat`, {
        data: {
          messages: [{ role: "user", content: "hi" }],
          device_type: "flagship",
          surface: "nonsense",
        },
      });
      expect(res.status()).toBe(422);
      expect(res.headers()["content-type"]).toContain("application/json");
    });
  });

  // -------------------------------------------------------------------
  // Browser apply-loop (Layer 4)
  //
  // Everything above proves the backend *emits* a validated tool_call.
  // It does not prove the browser applies it. That gap is where the
  // labelFor() drift lived: the drawer handled all 19 ops, the editor
  // panel handled 15, and no test looked. These drive the real drawer
  // and assert the server state actually changed.
  // -------------------------------------------------------------------
  test.describe("browser apply-loop", () => {
    /** The setup wizard holds every page behind a loader until a board exists. */
    async function stubBoard(request: APIRequestContext): Promise<void> {
      const res = await request.put(`${API_URL}/config/board`, {
        data: { api_mode: "local", local_api_key: "ai-e2e-stub", host: "127.0.0.1" },
      });
      expect(res.ok()).toBe(true);
    }

    async function openDrawer(page: import("@playwright/test").Page): Promise<void> {
      await page.goto("/");
      // The trigger only renders when an AI provider is configured.
      await page.getByRole("button", { name: "AI Assistant" }).first().click();
      await expect(page.getByRole("dialog", { name: /FiestaBot/i })).toBeVisible();
    }

    async function sendMessage(page: import("@playwright/test").Page, text: string): Promise<void> {
      const box = page
        .getByRole("dialog", { name: /FiestaBot/i })
        .getByRole("textbox")
        .first();
      await box.fill(text);
      await page.getByRole("button", { name: "Send", exact: true }).click();
    }

    test("a scripted create_schedule runs on the server and the panel shows the step", async ({ page, request }) => {
      await configureMockProvider(request);
      await stubBoard(request);

      // A page for the schedule to point at.
      const pageRes = await request.post(`${API_URL}/pages`, {
        data: {
          name: "Apply Loop Target",
          type: "template",
          device_type: "flagship",
          template: ["APPLY LOOP", "", "", "", "", ""],
          duration_seconds: 300,
        },
      });
      expect(pageRes.ok(), await pageRes.text()).toBe(true);
      const pageId = (await pageRes.json()).id as string;
      expect(pageId, "page id missing from POST /pages response").toBeTruthy();

      const before = await (await request.get(`${API_URL}/schedules`)).json();
      const beforeCount = (Array.isArray(before) ? before : before.schedules || []).length;

      await setMockScript({
        steps: [
          {
            prose: "Scheduling that for you.",
            ops: [{ op: "create_schedule", args: { page_id: pageId, start_time: "06:45", day_pattern: "all" } }],
          },
          { prose: "Scheduled for 06:45 every day." },
        ],
      });

      await openDrawer(page);
      await sendMessage(page, "schedule my page for the morning");

      const dialog = page.getByRole("dialog", { name: /FiestaBot/i });
      // The tool card is the observed step: it appears before the result
      // and settles to Done once the server has run the tool.
      await expect(dialog.getByTestId("ai-tool-create_schedule")).toBeVisible({ timeout: 15_000 });
      await expect(dialog.getByTestId("ai-tool-create_schedule")).toHaveAttribute("data-state", "output-available", {
        timeout: 15_000,
      });
      await expect(dialog.getByText(/Scheduled for 06:45/)).toBeVisible();

      const after = await (await request.get(`${API_URL}/schedules`)).json();
      const list = (Array.isArray(after) ? after : after.schedules || []) as Array<Record<string, unknown>>;
      expect(list.filter((s) => s.page_id === pageId && s.start_time === "06:45").length).toBeGreaterThan(0);
      expect(list.length).toBe(beforeCount + 1);
    });

    test("a destructive tool waits for Approve in the panel, and Deny leaves the page alone", async ({
      page,
      request,
    }) => {
      await configureMockProvider(request);
      await stubBoard(request);
      const pageRes = await request.post(`${API_URL}/pages`, {
        data: {
          name: "Keep Me",
          type: "template",
          device_type: "flagship",
          template: ["KEEP", "", "", "", "", ""],
          duration_seconds: 300,
        },
      });
      const pageId = (await pageRes.json()).id as string;

      await setMockScript({
        steps: [
          { prose: "Deleting it.", ops: [{ op: "delete_page", args: { page_id: pageId } }] },
          { prose: "Okay, leaving it." },
        ],
      });
      await openDrawer(page);
      await sendMessage(page, "delete the keep me page");

      const dialog = page.getByRole("dialog", { name: /FiestaBot/i });
      const approval = dialog.getByTestId("ai-approval-card");
      await expect(approval).toBeVisible({ timeout: 15_000 });
      // Nothing ran: the page is still there while the card is up.
      let pages = await (await request.get(`${API_URL}/pages`)).json();
      let list = (Array.isArray(pages) ? pages : pages.pages || []) as Array<Record<string, unknown>>;
      expect(list.some((p) => p.id === pageId)).toBe(true);

      await approval.getByRole("button", { name: "Deny" }).click();
      await expect(dialog.getByText(/leaving it/i)).toBeVisible({ timeout: 15_000 });
      await expect(dialog.getByTestId("ai-tool-delete_page")).toHaveAttribute("data-state", "denied");

      pages = await (await request.get(`${API_URL}/pages`)).json();
      list = (Array.isArray(pages) ? pages : pages.pages || []) as Array<Record<string, unknown>>;
      expect(list.some((p) => p.id === pageId)).toBe(true);
    });

    test("a question renders chips and choosing one resumes the conversation", async ({ page, request }) => {
      await configureMockProvider(request);
      await stubBoard(request);
      await setMockScript({
        steps: [
          { prose: "", ops: [{ op: "ask_user", args: { question: "Which board?", options: ["Kitchen", "Hall"] } }] },
          { prose: "Kitchen it is." },
        ],
      });
      await openDrawer(page);
      await sendMessage(page, "put the weather on a board");

      const dialog = page.getByRole("dialog", { name: /FiestaBot/i });
      const question = dialog.getByTestId("ai-question-card");
      await expect(question).toBeVisible({ timeout: 15_000 });
      await question.getByRole("button", { name: "Kitchen" }).click();

      await expect(dialog.getByText(/Kitchen it is/)).toBeVisible({ timeout: 15_000 });
      await expect(dialog.getByTestId("ai-question-answered")).toContainText("Kitchen");
    });
  });

  test.describe("walkthrough", () => {
    async function stubBoard(request: APIRequestContext): Promise<void> {
      const res = await request.put(`${API_URL}/config/board`, {
        data: { api_mode: "local", host: "127.0.0.1", local_api_key: "test-key" },
      });
      expect(res.ok(), await res.text()).toBe(true);
    }

    async function openDrawer(page: import("@playwright/test").Page, path = "/"): Promise<void> {
      await page.goto(path);
      await page.getByRole("button", { name: "AI Assistant" }).first().click();
      await expect(page.getByRole("dialog", { name: /FiestaBot/i })).toBeVisible();
    }

    async function sendMessage(page: import("@playwright/test").Page, text: string): Promise<void> {
      const box = page
        .getByRole("dialog", { name: /FiestaBot/i })
        .getByRole("textbox")
        .first();
      await box.fill(text);
      await page.getByRole("button", { name: "Send", exact: true }).click();
    }

    test("the stream announces a tool block while the model is still writing it", async ({ request }) => {
      await configureMockProvider(request);
      await setMockScript({
        prose: "Making it.",
        ops: [
          { op: "create_page", args: { name: "Streamed Page", template_lines: ["HELLO STREAM", "", "", "", "", ""] } },
        ],
      });
      const frames = await callChat(request, {
        messages: [{ role: "user", content: "make a page called Streamed Page" }],
        device_type: "flagship",
      });
      const kinds = frames.map((f) => f.event);
      expect(kinds).toContain("tool_streaming");
      expect(kinds.indexOf("tool_streaming")).toBeLessThan(kinds.indexOf("tool_call"));
      const drafts = frames.filter((f) => f.event === "tool_streaming");
      expect(drafts[drafts.length - 1].data.op).toBe("create_page");
      const pageId = (frames.find((f) => f.event === "tool_result")!.data.result as { page_id: string }).page_id;
      await request.delete(`${API_URL}/pages/${pageId}`);
    });

    test("create_page walks to a fresh editor, types the page, and lands on the saved page", async ({
      page,
      request,
    }) => {
      await configureMockProvider(request);
      await stubBoard(request);
      await setMockScript({
        steps: [
          {
            prose: "Building it.",
            ops: [
              {
                op: "create_page",
                args: { name: "Walked Page", template_lines: ["GOOD MORNING", "", "", "", "", ""] },
              },
            ],
          },
          { prose: "Done, it is open." },
        ],
      });
      await openDrawer(page, "/settings");
      await sendMessage(page, "make me a page called Walked Page");

      // The spotlight narrates on screen, outside the chat dialog.
      const caption = page.getByTestId("ai-spotlight-caption");
      await expect(caption).toBeVisible({ timeout: 15_000 });
      // The editor opens (via the Pages list) and the name is typed for real.
      await expect(page).toHaveURL(/\/pages\/(new|edit\/)/, { timeout: 15_000 });
      await expect(page.getByLabel(/page name/i)).toHaveValue("Walked Page", { timeout: 15_000 });
      // It settles on the saved page, and the server has it.
      await expect(page).toHaveURL(/\/pages\/edit\/[0-9a-f-]+/, { timeout: 20_000 });
      await expect(caption).toHaveText(/Page created/i, { timeout: 15_000 });
      const pages = await (await request.get(`${API_URL}/pages`)).json();
      const list = (Array.isArray(pages) ? pages : pages.pages || []) as Array<Record<string, unknown>>;
      const created = list.find((p) => p.name === "Walked Page");
      expect(created).toBeTruthy();
      // The staged draft left nothing behind for /pages/new to restore.
      await page.goto("/pages/new");
      await expect(page.getByText(/draft restored/i)).toHaveCount(0);
      await request.delete(`${API_URL}/pages/${created!.id}`);
    });

    test("update_setting goes to the tab, ghosts the value over its control, and pulses the card", async ({
      page,
      request,
    }) => {
      await configureMockProvider(request);
      await stubBoard(request);
      await setMockScript({
        steps: [
          {
            prose: "Renaming.",
            ops: [{ op: "update_setting", args: { category: "general", values: { instance_name: "Kitchen Board" } } }],
          },
          { prose: "Renamed." },
        ],
      });
      await openDrawer(page, "/pages");
      await sendMessage(page, "rename my board to Kitchen Board");

      await expect(page).toHaveURL(/\/settings\?section=general/, { timeout: 15_000 });
      const ghost = page.getByTestId("ai-ghost");
      await expect(ghost.first()).toBeVisible({ timeout: 15_000 });
      await expect(ghost.first()).toContainText("Kitchen Board");
      await expect(page.getByTestId("ai-spotlight-caption")).toHaveText(/Setting saved/i, { timeout: 15_000 });
      // The real value landed on the control the ghost pointed at.
      await expect(page.locator("#instance-name")).toHaveValue("Kitchen Board", { timeout: 15_000 });
      // The ring is gone once the walkthrough settles.
      await expect(page.getByTestId("ai-spotlight-ring")).toHaveCount(0, { timeout: 10_000 });
    });

    test("Stop mid-walkthrough discards the staged page and leaves the editor clean", async ({ page, request }) => {
      await configureMockProvider(request);
      await stubBoard(request);
      // A slow tool: the create waits on approval-free but the mock delays the model's next turn.
      await setMockScript({
        steps: [
          {
            prose: "Building it.",
            ops: [
              {
                op: "create_page",
                args: { name: "Stopped Page", template_lines: ["ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX"] },
              },
            ],
          },
          { prose: "Anything else?" },
        ],
      });
      await openDrawer(page, "/settings");
      await sendMessage(page, "make a page called Stopped Page");
      await expect(page).toHaveURL(/\/pages\/(new|edit\/)/, { timeout: 15_000 });
      // Stop as soon as the walkthrough is on screen.
      await page.getByTestId("ai-spotlight-caption").getByRole("button", { name: "Stop" }).click({ timeout: 15_000 });
      await expect(page.getByTestId("ai-spotlight-ring")).toHaveCount(0, { timeout: 10_000 });
      // Whatever was staged is gone: nothing typed lingers in a draft.
      await page.goto("/pages/new");
      await expect(page.getByText(/draft restored/i)).toHaveCount(0);
      const pages = await (await request.get(`${API_URL}/pages`)).json();
      const list = (Array.isArray(pages) ? pages : pages.pages || []) as Array<Record<string, unknown>>;
      for (const p of list.filter((p) => p.name === "Stopped Page")) await request.delete(`${API_URL}/pages/${p.id}`);
    });
  });
});
