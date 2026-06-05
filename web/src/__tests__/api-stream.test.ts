import { beforeEach, describe, expect, it, vi } from "vitest";

import { streamChat } from "@/lib/api-stream";

// Mock the SSE library — the real one opens a persistent HTTP connection
// which has no place in a unit test.
vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn(),
}));

import { fetchEventSource } from "@microsoft/fetch-event-source";
const mockFES = fetchEventSource as ReturnType<typeof vi.fn>;

const BASE_BODY = {
  messages: [{ role: "user" as const, content: "hello" }],
  device_type: "flagship" as const,
};

beforeEach(() => {
  mockFES.mockReset();
});

describe("streamChat", () => {
  it("POSTs to /api/pages/ai/chat with JSON body", async () => {
    mockFES.mockResolvedValue(undefined);
    await streamChat(BASE_BODY, {});
    expect(mockFES).toHaveBeenCalledWith(
      "/api/pages/ai/chat",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(BASE_BODY),
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      }),
    );
  });

  it("fires onText handler for 'text' events", async () => {
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      opts.onmessage?.({ event: "text", data: JSON.stringify({ delta: "hello " }), id: "", retry: undefined });
      opts.onmessage?.({ event: "text", data: JSON.stringify({ delta: "world" }), id: "", retry: undefined });
    });
    const onText = vi.fn();
    await streamChat(BASE_BODY, { onText });
    expect(onText).toHaveBeenCalledWith("hello ");
    expect(onText).toHaveBeenCalledWith("world");
  });

  it("fires onToolCall handler for 'tool_call' events", async () => {
    const payload = {
      id: "tc1",
      op: "replace_page",
      args: { name: "p", template: [], line_metadata: [], duration_seconds: 300 },
    };
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      opts.onmessage?.({ event: "tool_call", data: JSON.stringify(payload), id: "", retry: undefined });
    });
    const onToolCall = vi.fn();
    await streamChat(BASE_BODY, { onToolCall });
    expect(onToolCall).toHaveBeenCalledWith({ id: "tc1", op: "replace_page", args: payload.args });
  });

  it("fires onWarning handler for 'warning' events", async () => {
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      opts.onmessage?.({ event: "warning", data: JSON.stringify({ message: "slow model" }), id: "", retry: undefined });
    });
    const onWarning = vi.fn();
    await streamChat(BASE_BODY, { onWarning });
    expect(onWarning).toHaveBeenCalledWith("slow model");
  });

  it("fires onError and aborts for 'error' events", async () => {
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      opts.onmessage?.({ event: "error", data: JSON.stringify({ message: "oops" }), id: "", retry: undefined });
    });
    const onError = vi.fn();
    await streamChat(BASE_BODY, { onError });
    expect(onError).toHaveBeenCalledWith("oops");
  });

  it("fires onDone for 'done' events", async () => {
    const done = {
      model_used: "m",
      provider_id: "p",
      usage: { prompt_tokens: 10, completion_tokens: 20, total_tokens: 30 },
    };
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      opts.onmessage?.({ event: "done", data: JSON.stringify(done), id: "", retry: undefined });
    });
    const onDone = vi.fn();
    await streamChat(BASE_BODY, { onDone });
    expect(onDone).toHaveBeenCalledWith(done);
  });

  it("ignores messages with no event field", async () => {
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      opts.onmessage?.({ event: "", data: "{}", id: "", retry: undefined });
    });
    const onText = vi.fn();
    await streamChat(BASE_BODY, { onText });
    expect(onText).not.toHaveBeenCalled();
  });

  it("ignores malformed JSON in message data", async () => {
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      opts.onmessage?.({ event: "text", data: "not-json", id: "", retry: undefined });
    });
    const onText = vi.fn();
    await streamChat(BASE_BODY, { onText });
    expect(onText).not.toHaveBeenCalled();
  });

  it("surfaces non-2xx response via onError", async () => {
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      const response = {
        ok: false,
        status: 500,
        headers: { get: () => null },
        json: async () => ({ detail: "internal error" }),
      };
      await opts.onopen?.(response);
    });
    const onError = vi.fn();
    await streamChat(BASE_BODY, { onError });
    expect(onError).toHaveBeenCalledWith("internal error");
  });

  it("reports unexpected content-type on successful response", async () => {
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      const response = { ok: true, status: 200, headers: { get: () => "application/json" } };
      await opts.onopen?.(response);
    });
    const onError = vi.fn();
    await streamChat(BASE_BODY, { onError });
    expect(onError).toHaveBeenCalledWith(expect.stringContaining("Unexpected response type"));
  });

  it("aborts cleanly when an AbortSignal fires", async () => {
    const ctrl = new AbortController();
    mockFES.mockImplementation(async (_url: string, _opts: any) => {
      // Simulate a long-running stream — the signal fires externally
    });
    // Pre-abort
    ctrl.abort();
    await expect(streamChat(BASE_BODY, {}, ctrl.signal)).resolves.toBeUndefined();
  });

  it("calls onerror and surfaces non-abort errors", async () => {
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      await opts.onerror?.(new Error("network failure"));
    });
    const onError = vi.fn();
    await streamChat(BASE_BODY, { onError });
    expect(onError).toHaveBeenCalledWith("network failure");
  });

  it("swallows AbortError from onerror (clean close)", async () => {
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      const err = new DOMException("Aborted", "AbortError");
      // throwing AbortError from onerror causes fetchEventSource to stop
      try {
        opts.onerror?.(err);
      } catch {
        // expected — onerror throws to terminate
      }
    });
    const onError = vi.fn();
    await expect(streamChat(BASE_BODY, { onError })).resolves.toBeUndefined();
    expect(onError).not.toHaveBeenCalled();
  });

  it("registers and cleans up abort listener for a non-pre-aborted signal", async () => {
    const ctrl = new AbortController();
    mockFES.mockResolvedValue(undefined);
    // Signal is NOT pre-aborted — takes the addEventListener path
    await expect(streamChat(BASE_BODY, {}, ctrl.signal)).resolves.toBeUndefined();
  });

  it("falls back to status text when server JSON has no detail field", async () => {
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      const response = {
        ok: false,
        status: 503,
        headers: { get: () => null },
        json: async () => ({ other: "data" }),
      };
      await opts.onopen?.(response);
    });
    const onError = vi.fn();
    await streamChat(BASE_BODY, { onError });
    expect(onError).toHaveBeenCalledWith("Server returned 503.");
  });

  it("handles a server error response whose JSON cannot be parsed", async () => {
    mockFES.mockImplementation(async (_url: string, opts: any) => {
      const response = {
        ok: false,
        status: 502,
        headers: { get: () => null },
        json: async () => {
          throw new SyntaxError("bad json");
        },
      };
      await opts.onopen?.(response);
    });
    const onError = vi.fn();
    await streamChat(BASE_BODY, { onError });
    expect(onError).toHaveBeenCalledWith("Server returned 502.");
  });
});
