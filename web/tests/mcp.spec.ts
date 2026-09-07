/**
 * MCP E2E tests.
 *
 * Smoke-tests the FastMCP server mounted at `/api/mcp`. The intent is
 * narrow: confirm the server is reachable, speaks MCP Streamable-HTTP
 * (JSON-RPC 2.0 over POST), and exposes the tools we expect. We do NOT
 * try to round-trip every tool here — that's what tests/test_mcp_server.py
 * does at the unit level. This spec catches "MCP got broken at the HTTP
 * boundary" regressions (wrong mount path, dropped headers, package
 * disabled, etc.) that unit tests can't see.
 *
 * Gated behind RUN_AI_TESTS in playwright.config.ts because it shares a
 * CI job with the AI e2e suite.
 */
import { type APIRequestContext, expect, test } from "@playwright/test";

const BASE_URL = process.env.BASE_URL || "http://localhost:4420";
// The FastMCP app is mounted at /mcp by api_server.py and exposed via
// nginx at /api/mcp. The streamable_http_path inside FastMCP is "/", so
// the actual endpoint is /api/mcp/ (trailing slash matters under starlette
// mounts).
const MCP_URL = `${BASE_URL}/api/mcp/`;

const MCP_PROTOCOL_VERSION = "2024-11-05";

type JsonRpcRequest = {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: Record<string, unknown>;
};

type JsonRpcResponse = {
  jsonrpc: "2.0";
  id: number;
  result?: Record<string, unknown>;
  error?: { code: number; message: string; data?: unknown };
};

/**
 * POST a JSON-RPC request to the MCP endpoint with the headers FastMCP's
 * Streamable HTTP transport requires.
 */
async function rpc(
  request: APIRequestContext,
  body: JsonRpcRequest,
  sessionId?: string,
): Promise<{ status: number; body: JsonRpcResponse; sessionId?: string }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    // The Streamable HTTP spec requires both JSON and SSE to be accepted —
    // FastMCP returns 406 if you only ask for application/json.
    Accept: "application/json, text/event-stream",
  };
  if (sessionId) {
    headers["Mcp-Session-Id"] = sessionId;
  }
  const res = await request.post(MCP_URL, {
    headers,
    data: body,
  });
  const status = res.status();
  const responseSession = res.headers()["mcp-session-id"];
  // FastMCP may return either plain JSON (json_response=True) or SSE.
  // The mounted instance sets json_response=True so this should always
  // parse as JSON, but stay defensive in case that changes.
  const text = await res.text();
  let parsed: JsonRpcResponse;
  try {
    parsed = JSON.parse(text) as JsonRpcResponse;
  } catch {
    throw new Error(`MCP response was not JSON (status ${status}). First 200 chars: ${text.slice(0, 200)}`);
  }
  return { status, body: parsed, sessionId: responseSession };
}

async function initialize(request: APIRequestContext): Promise<{ sessionId?: string; protocolVersion?: string }> {
  const res = await rpc(request, {
    jsonrpc: "2.0",
    id: 1,
    method: "initialize",
    params: {
      protocolVersion: MCP_PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: { name: "fiestaboard-e2e", version: "1.0" },
    },
  });
  expect(res.status, `initialize: HTTP ${res.status}`).toBeLessThan(400);
  expect(res.body.error, JSON.stringify(res.body.error)).toBeUndefined();
  const result = res.body.result || {};
  return {
    sessionId: res.sessionId,
    protocolVersion: typeof result.protocolVersion === "string" ? result.protocolVersion : undefined,
  };
}

test.describe("MCP", () => {
  test("endpoint is mounted (not 404)", async ({ request }) => {
    // An empty POST isn't a valid MCP request, but the server should still
    // respond with something — a 400 JSON-RPC validation error — proving
    // the mount is live. A 404 means the package failed to load and the
    // mount was silently disabled (see api_server.py). Don't probe with
    // GET: since mcp 2.0 that opens a never-ending SSE listen stream and
    // the request would hang until the test timeout.
    const res = await request.post(MCP_URL, {
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
      },
      data: {},
    });
    expect(res.status()).not.toBe(404);
  });

  test("initialize handshake succeeds", async ({ request }) => {
    const { protocolVersion } = await initialize(request);
    // The server should echo a protocol version. We don't pin the exact
    // string because the MCP SDK bumps it over time and we don't want a
    // dependency upgrade to break this test.
    expect(protocolVersion, "server returned no protocolVersion").toBeTruthy();
  });

  test("tools/list returns the FiestaBoard tool catalog", async ({ request }) => {
    const { sessionId } = await initialize(request);

    const res = await rpc(request, { jsonrpc: "2.0", id: 2, method: "tools/list" }, sessionId);
    expect(res.status).toBeLessThan(400);
    expect(res.body.error).toBeUndefined();

    const tools = (res.body.result?.tools || []) as Array<{ name: string }>;
    expect(Array.isArray(tools)).toBe(true);
    expect(tools.length).toBeGreaterThan(0);

    const names = new Set(tools.map((t) => t.name));
    // A representative sample across plugin / page / schedule surfaces.
    // If any of these go missing the MCP contract has shifted in a way
    // external integrators will notice.
    for (const expected of [
      "list_installed_plugins",
      "list_pages",
      "get_page",
      "create_page",
      "list_schedules",
      "get_system_status",
    ]) {
      expect(names.has(expected), `missing tool: ${expected}`).toBe(true);
    }
  });

  test("tools/call list_pages returns structured payload", async ({ request }) => {
    const { sessionId } = await initialize(request);

    const res = await rpc(
      request,
      {
        jsonrpc: "2.0",
        id: 3,
        method: "tools/call",
        params: { name: "list_pages", arguments: {} },
      },
      sessionId,
    );
    expect(res.status).toBeLessThan(400);
    expect(res.body.error).toBeUndefined();

    // Per the MCP spec, tools whose return is a structured value (dict /
    // list / BaseModel) populate `structuredContent`. Tools that return a
    // raw string populate `content` with a TextContent block. We accept
    // either — list_pages now returns a structured list so we'll see
    // `structuredContent`, but some other tools may still text-respond.
    const result = res.body.result || {};
    const structured = result.structuredContent;
    const content = (result.content || []) as Array<{ type: string; text?: string }>;

    if (structured !== undefined) {
      // structuredContent is the source of truth for structured returns.
      // For list_pages it wraps the array under a `result` key.
      const payload =
        typeof structured === "object" && structured !== null && "result" in structured
          ? (structured as { result: unknown }).result
          : structured;
      expect(Array.isArray(payload) || typeof payload === "object").toBe(true);
    } else {
      // Fallback: text-mode tool. Must have a parseable JSON text block.
      expect(content.length).toBeGreaterThan(0);
      const textBlock = content.find((b) => b.type === "text" && typeof b.text === "string");
      expect(textBlock, "no text block and no structuredContent").toBeDefined();
      expect(() => JSON.parse(textBlock!.text as string)).not.toThrow();
    }
  });

  test("unknown tool name is reported as a JSON-RPC error", async ({ request }) => {
    const { sessionId } = await initialize(request);

    const res = await rpc(
      request,
      {
        jsonrpc: "2.0",
        id: 4,
        method: "tools/call",
        params: { name: "this_tool_does_not_exist", arguments: {} },
      },
      sessionId,
    );
    // Either a JSON-RPC error (preferred) or an HTTP 4xx — both are
    // acceptable signs the server is validating tool names.
    if (res.status >= 400) {
      // HTTP-level rejection is fine.
      return;
    }
    expect(res.body.error || res.body.result?.isError).toBeTruthy();
  });

  // ===================================================================
  // Layer 5 — skill scenarios
  //
  // Everything above proves the transport works and that one tool
  // responds. None of it proves a *skill* works. The MCP surface is 28
  // tools, 5 prompts and 6 resources, and what a client actually runs is
  // a chain across them. The prompts are the skill definitions.
  // ===================================================================

  /** tools/call, unwrapping the structured payload MCP wraps returns in. */
  async function callTool(
    request: APIRequestContext,
    sessionId: string | undefined,
    name: string,
    args: Record<string, unknown> = {},
    id = 100,
  ): Promise<unknown> {
    const res = await rpc(
      request,
      { jsonrpc: "2.0", id, method: "tools/call", params: { name, arguments: args } },
      sessionId,
    );
    expect(res.status, `${name}: HTTP ${res.status}`).toBeLessThan(400);
    expect(res.body.error, `${name}: ${JSON.stringify(res.body.error)}`).toBeUndefined();

    const result = res.body.result || {};
    const structured = result.structuredContent;
    if (structured !== undefined) {
      return typeof structured === "object" && structured !== null && "result" in structured
        ? (structured as { result: unknown }).result
        : structured;
    }
    const content = (result.content || []) as Array<{ type: string; text?: string }>;
    const textBlock = content.find((b) => b.type === "text" && typeof b.text === "string");
    expect(textBlock, `${name}: no structuredContent and no text block`).toBeDefined();
    try {
      return JSON.parse(textBlock!.text as string);
    } catch {
      return textBlock!.text;
    }
  }

  /** Fail loudly with the tool's own error string rather than a shape mismatch. */
  function expectNoToolError(payload: unknown, what: string): Record<string, unknown> {
    const obj = payload as Record<string, unknown>;
    expect(obj, `${what} returned nothing`).toBeTruthy();
    expect(obj.error, `${what} failed: ${JSON.stringify(obj.error)}`).toBeFalsy();
    return obj;
  }

  test.describe("protocol lifecycle", () => {
    test("initialize then list tools, prompts and resources", async ({ request }) => {
      const { sessionId, protocolVersion } = await initialize(request);
      expect(protocolVersion, "server did not negotiate a protocol version").toBeTruthy();

      const tools = await rpc(request, { jsonrpc: "2.0", id: 10, method: "tools/list" }, sessionId);
      expect(((tools.body.result?.tools || []) as unknown[]).length).toBeGreaterThanOrEqual(28);

      const prompts = await rpc(request, { jsonrpc: "2.0", id: 11, method: "prompts/list" }, sessionId);
      expect(prompts.body.error, JSON.stringify(prompts.body.error)).toBeUndefined();
      expect(((prompts.body.result?.prompts || []) as unknown[]).length).toBeGreaterThanOrEqual(5);

      const resources = await rpc(request, { jsonrpc: "2.0", id: 12, method: "resources/list" }, sessionId);
      expect(resources.body.error, JSON.stringify(resources.body.error)).toBeUndefined();
      expect(((resources.body.result?.resources || []) as unknown[]).length).toBeGreaterThanOrEqual(5);
    });
  });

  test.describe("prompts", () => {
    // The skill definitions. Before this, nothing executed a single one.
    for (const name of [
      "setup_fiestaboard",
      "create_display_page",
      "schedule_my_day",
      "build_a_collection",
      "troubleshoot_display",
    ]) {
      test(`prompts/get ${name} returns usable messages`, async ({ request }) => {
        const { sessionId } = await initialize(request);
        const res = await rpc(
          request,
          { jsonrpc: "2.0", id: 20, method: "prompts/get", params: { name, arguments: {} } },
          sessionId,
        );
        expect(res.status, `${name}: HTTP ${res.status}`).toBeLessThan(400);
        expect(res.body.error, `${name}: ${JSON.stringify(res.body.error)}`).toBeUndefined();

        const messages = (res.body.result?.messages || []) as Array<{
          role: string;
          content: { type: string; text?: string };
        }>;
        expect(messages.length, `${name} rendered no messages`).toBeGreaterThan(0);
        const text = messages.map((m) => m.content?.text || "").join("\n");
        expect(text.trim().length, `${name} rendered empty text`).toBeGreaterThan(40);
      });
    }
  });

  test.describe("resources", () => {
    for (const uri of [
      "fiestaboard://plugins",
      "fiestaboard://pages",
      "fiestaboard://variables",
      "fiestaboard://schedules",
      "fiestaboard://collections",
    ]) {
      test(`resources/read ${uri} returns content`, async ({ request }) => {
        const { sessionId } = await initialize(request);
        const res = await rpc(
          request,
          { jsonrpc: "2.0", id: 30, method: "resources/read", params: { uri } },
          sessionId,
        );
        expect(res.status, `${uri}: HTTP ${res.status}`).toBeLessThan(400);
        expect(res.body.error, `${uri}: ${JSON.stringify(res.body.error)}`).toBeUndefined();

        const contents = (res.body.result?.contents || []) as Array<{ text?: string; mimeType?: string }>;
        expect(contents.length, `${uri} returned no contents`).toBeGreaterThan(0);
        expect((contents[0].text || "").trim().length, `${uri} returned empty text`).toBeGreaterThan(0);
      });
    }

    test("the page preview URI template renders HTML for a real page", async ({ request }) => {
      const { sessionId } = await initialize(request);
      const created = expectNoToolError(
        await callTool(request, sessionId, "create_page", {
          name: "MCP Preview Target",
          template_lines: ["PREVIEW", "", "", "", "", ""],
          device_type: "flagship",
        }),
        "create_page",
      );

      const res = await rpc(
        request,
        {
          jsonrpc: "2.0",
          id: 31,
          method: "resources/read",
          params: { uri: `fiestaboard://page/${created.page_id}/preview.html` },
        },
        sessionId,
      );
      expect(res.body.error, JSON.stringify(res.body.error)).toBeUndefined();
      const contents = (res.body.result?.contents || []) as Array<{ text?: string }>;
      expect(contents.length).toBeGreaterThan(0);
      expect(contents[0].text || "").toContain("<");
    });
  });

  test.describe("multi-tool chains", () => {
    // Individual tool correctness does not prove a chain completes: state
    // produced by tool 3 has to be shaped right for tool 5. This is the
    // closest deterministic proxy for "a skill works".

    test("create a page, schedule it, and see both in a re-read", async ({ request }) => {
      const { sessionId } = await initialize(request);

      const created = expectNoToolError(
        await callTool(request, sessionId, "create_page", {
          name: "Chain Morning Page",
          template_lines: ["GOOD MORNING", "", "", "", "", ""],
          device_type: "flagship",
        }),
        "create_page",
      );
      const pageId = created.page_id as string;
      expect(pageId).toBeTruthy();

      const scheduled = expectNoToolError(
        await callTool(request, sessionId, "create_schedule", {
          page_id: pageId,
          start_time: "07:30",
          day_pattern: "all",
        }),
        "create_schedule",
      );
      const scheduleId = scheduled.schedule_id as string;

      // Re-read through different tools — the chain is only real if the
      // state it produced is visible to a fresh call.
      const pages = (await callTool(request, sessionId, "list_pages", {}, 101)) as Array<Record<string, unknown>>;
      expect(pages.some((p) => p.id === pageId)).toBe(true);

      const schedules = (await callTool(request, sessionId, "list_schedules", {}, 102)) as Array<
        Record<string, unknown>
      >;
      const mine = schedules.find((s) => s.id === scheduleId);
      expect(mine, "schedule vanished between create and list").toBeTruthy();
      expect(mine!.page_id).toBe(pageId);
      expect(mine!.start_time).toBe("07:30");
    });

    test("rename a page mid-chain without destroying it", async ({ request }) => {
      // Regression for the partial-update bug: update_page passed
      // template=None on every call, wiping the template and failing
      // validation, so renaming over MCP was impossible.
      const { sessionId } = await initialize(request);

      const created = expectNoToolError(
        await callTool(request, sessionId, "create_page", {
          name: "Chain Before",
          template_lines: ["KEEP ME", "", "", "", "", ""],
          device_type: "flagship",
        }),
        "create_page",
      );
      const pageId = created.page_id as string;

      expectNoToolError(
        await callTool(request, sessionId, "update_page", { page_id: pageId, name: "Chain After" }, 103),
        "update_page (name only)",
      );

      const page = expectNoToolError(
        await callTool(request, sessionId, "get_page", { page_id: pageId }, 104),
        "get_page",
      );
      expect(page.name).toBe("Chain After");
      expect(page.template, "renaming destroyed the template").toEqual(["KEEP ME", "", "", "", "", ""]);
    });

    test("collect pages, then delete the collection and a page", async ({ request }) => {
      // Exercises delete_page over the real transport — it read
      // DeleteResult.success, an attribute that does not exist, so it
      // never deleted anything.
      const { sessionId } = await initialize(request);

      const a = expectNoToolError(
        await callTool(request, sessionId, "create_page", {
          name: "Chain Collected A",
          template_lines: ["A", "", "", "", "", ""],
          device_type: "flagship",
        }),
        "create_page A",
      );
      const b = expectNoToolError(
        await callTool(
          request,
          sessionId,
          "create_page",
          {
            name: "Chain Collected B",
            template_lines: ["B", "", "", "", "", ""],
            device_type: "flagship",
          },
          105,
        ),
        "create_page B",
      );

      const collection = expectNoToolError(
        await callTool(
          request,
          sessionId,
          "create_collection",
          { name: "Chain Collection", page_ids: [a.page_id, b.page_id] },
          106,
        ),
        "create_collection",
      );
      const collectionId = collection.collection_id as string;

      const collections = (await callTool(request, sessionId, "list_collections", {}, 107)) as Array<
        Record<string, unknown>
      >;
      expect(collections.some((c) => c.id === collectionId)).toBe(true);

      expectNoToolError(
        await callTool(request, sessionId, "delete_collection", { collection_id: collectionId }, 108),
        "delete_collection",
      );
      expectNoToolError(await callTool(request, sessionId, "delete_page", { page_id: b.page_id }, 109), "delete_page");

      const afterCollections = (await callTool(request, sessionId, "list_collections", {}, 110)) as Array<
        Record<string, unknown>
      >;
      expect(afterCollections.some((c) => c.id === collectionId)).toBe(false);

      const afterPages = (await callTool(request, sessionId, "list_pages", {}, 111)) as Array<Record<string, unknown>>;
      expect(
        afterPages.some((p) => p.id === b.page_id),
        "delete_page did not delete",
      ).toBe(false);
    });

    test("render_page_preview does not persist a page", async ({ request }) => {
      const { sessionId } = await initialize(request);
      const before = (await callTool(request, sessionId, "list_pages", {}, 112)) as unknown[];

      expectNoToolError(
        await callTool(
          request,
          sessionId,
          "render_page_preview",
          { template_lines: ["PREVIEW ONLY", "", "", "", "", ""], device_type: "flagship" },
          113,
        ),
        "render_page_preview",
      );

      const after = (await callTool(request, sessionId, "list_pages", {}, 114)) as unknown[];
      expect(after.length).toBe(before.length);
    });
  });
});
