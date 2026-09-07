// AI domain: BYO-LLM provider settings and one-shot page generation.
// The chat SSE stream lives in lib/api-stream.ts.

import { apiUrl } from "../base-path";
import { fetchApi } from "./core";
import type { DeviceType, LineMetadata } from "./shared";

export type AIProviderProtocol = "openai" | "anthropic";

export interface AIProvider {
  id: string;
  name: string;
  protocol?: AIProviderProtocol;
  base_url: string;
  api_key: string;
  models: string[];
  default_model?: string;
  headers?: Record<string, string>;
}

export interface AISettings {
  enabled: boolean;
  providers: AIProvider[];
  default_provider_id: string | null;
}

export interface AITestResult {
  ok: boolean;
  message: string;
  model_used: string | null;
}

export interface AIPageWarning {
  message: string;
}

/**
 * Mirrors `AIGenerateResponse` in `src/ai/page_routes.py`.
 *
 * `page` is a `PageCreate`-shaped **draft**, not a stored page — this
 * endpoint never writes, and the editor holds the draft locally until the
 * user clicks Save. Since the route declares its response model, every
 * optional `PageCreate` field the generator did not set arrives as `null`
 * rather than being absent, so they are typed that way here.
 */
export interface AIGeneratedPageDraft {
  name: string;
  type: "template";
  device_type: DeviceType;
  template: string[];
  line_metadata: LineMetadata[];
  duration_seconds: number;
  display_type: string | null;
  rows: unknown[] | null;
  transition_strategy: string | null;
  transition_interval_ms: number | null;
  transition_step_size: number | null;
  demo_plugin_id: string | null;
  notes_wide: number | null;
  notes_tall: number | null;
}

export interface AIGenerateResult {
  page: AIGeneratedPageDraft;
  model_used: string;
  provider_id: string | null;
  warnings: string[];
  usage: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
  };
}

/**
 * The result of one chat operation executed server-side.
 *
 * Mirrors `OperationResponse` in `src/ai/routes.py`. `status` is always
 * `"success"` — a failed operation is an HTTP error, so `fetchApi` throws
 * an `ApiError` carrying the executor's message and the caller never sees
 * a sad 200. `result` carries whatever the executor returned beyond the
 * envelope (`schedule_id`, `plugin_id`, `collection_id`, ...).
 */
export interface AiOperationResult {
  op: string;
  status: "success";
  message: string;
  result: Record<string, unknown>;
}

export const aiApi = {
  /**
   * Execute one chat-grammar tool call on the server.
   *
   * The single seam replacing the drawer's former per-op REST dispatcher
   * (Phase 2 Task 11). The server validates `args` against the same
   * pydantic schema that validated the SSE `tool_call` frame, then runs
   * the one canonical executor the MCP tools also use — which is what
   * stops the two AI surfaces drifting.
   *
   * Client-side ops (`apply_patch`, `replace_page`, `suggest_variables`,
   * `navigate_to_page`, `navigate_to_schedule`, `update_task_list`) are
   * refused with a 400: they edit the mounted editor or navigate, and are
   * applied in the browser.
   */
  executeAiOperation: (op: string, args: Record<string, unknown>) =>
    fetchApi<AiOperationResult>("/ai/operations", {
      method: "POST",
      body: JSON.stringify({ op, args }),
      // Plugin installs clone a git repo; the default 30s is too tight.
      timeoutMs: 120000,
    }),

  // AI page-generation ("Gen AI" button) settings + endpoints. BYO-LLM:
  // users supply their own OpenAI-compatible endpoint and key. The API
  // key is masked on read; sending "***" preserves the stored value.
  getAiSettings: () => fetchApi<AISettings>("/settings/ai"),

  updateAiSettings: (updates: Partial<AISettings>) =>
    fetchApi<AISettings>("/settings/ai", {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  testAiProvider: (params: { provider_id?: string; model?: string; provider?: AIProvider }) =>
    fetchApi<AITestResult>("/settings/ai/test", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  generateAiPage: async (params: {
    prompt: string;
    device_type: DeviceType;
    provider_id?: string;
    model?: string;
    current_page?: unknown;
  }): Promise<AIGenerateResult> => {
    // Bespoke fetch so we can surface the FastAPI `detail` message
    // (the LLM's own error text) directly to the user.
    const res = await fetch(apiUrl("/pages/ai/generate"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
      // Generous timeout — LLM calls can take 30s+.
      signal: AbortSignal.timeout(120000),
    });
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const body = (await res.json()) as { detail?: unknown };
        // A hand-raised failure is `{detail: string}`; FastAPI's own schema
        // rejection (422) is `{detail: [...]}`. Serialize the latter rather
        // than dropping it, matching what `fetchApi` in api/core.ts does.
        if (body && body.detail !== undefined) {
          detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        }
      } catch {
        // Ignore JSON parse errors; fall back to status text.
      }
      throw new Error(detail);
    }
    return (await res.json()) as AIGenerateResult;
  },
};
