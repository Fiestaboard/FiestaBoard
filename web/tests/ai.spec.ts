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
 * Streaming /chat is intentionally NOT covered here — it's unit-tested and
 * Playwright SSE handling is complex enough to warrant its own PR.
 */
import { test, expect, type APIRequestContext } from "@playwright/test";

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

    test("rejects bogus device_type with 400", async ({ request }) => {
      const res = await request.get(`${API_URL}/pages/ai/context?device_type=potato`);
      expect(res.status()).toBe(400);
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

    test("returns 400 when prompt is missing", async ({ request }) => {
      await configureMockProvider(request);
      const { status } = await callGenerate(request, {
        device_type: "flagship",
      });
      expect(status).toBe(400);
    });

    test("happy path round-trips through the mock and returns a valid page", async ({
      request,
    }) => {
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

    test("surfaces upstream auth error as a 400 with the provider message", async ({
      request,
    }) => {
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

    test("returns 400 when the model omits the required template field", async ({
      request,
    }) => {
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
      await expect(
        page.getByText(/AI Providers|AI Settings|Add provider/i).first(),
      ).toBeVisible();
      // The provider we configured via the API should appear in the list.
      await expect(page.getByText(PROVIDER_NAME, { exact: false }).first()).toBeVisible();
    });
  });
});
