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
import { test, expect, type APIRequestContext } from "@playwright/test";

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
    throw new Error(
      `MCP response was not JSON (status ${status}). First 200 chars: ${text.slice(0, 200)}`,
    );
  }
  return { status, body: parsed, sessionId: responseSession };
}

async function initialize(
  request: APIRequestContext,
): Promise<{ sessionId?: string; protocolVersion?: string }> {
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
    protocolVersion: typeof result.protocolVersion === "string"
      ? result.protocolVersion
      : undefined,
  };
}

test.describe("MCP", () => {
  test("endpoint is mounted (not 404)", async ({ request }) => {
    // A bare GET on the streamable endpoint won't be a valid MCP request,
    // but the server should still respond with something — 405/400/406 —
    // proving the mount is live. A 404 means the package failed to load
    // and FastMCP silently disabled the mount (see api_server.py:776).
    const res = await request.get(MCP_URL);
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

    const res = await rpc(
      request,
      { jsonrpc: "2.0", id: 2, method: "tools/list" },
      sessionId,
    );
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

  test("tools/call list_pages returns valid JSON content", async ({ request }) => {
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

    // MCP tools/call results carry a `content` array of typed blocks; for
    // text tools FastMCP wraps the return value as {type:"text", text:"..."}.
    const result = res.body.result || {};
    const content = (result.content || []) as Array<{ type: string; text?: string }>;
    expect(Array.isArray(content)).toBe(true);
    expect(content.length).toBeGreaterThan(0);
    const textBlock = content.find((b) => b.type === "text" && typeof b.text === "string");
    expect(textBlock, "no text block in tools/call result").toBeDefined();

    // list_pages returns JSON-encoded text. It must parse.
    expect(() => JSON.parse(textBlock!.text as string)).not.toThrow();
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
});
