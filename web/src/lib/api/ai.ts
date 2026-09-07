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

export interface AIGenerateResult {
  page: {
    name: string;
    type: "template";
    device_type: DeviceType;
    template: string[];
    line_metadata: LineMetadata[];
    duration_seconds: number;
  };
  model_used: string;
  provider_id: string;
  warnings: string[];
  usage: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
  };
}

export const aiApi = {
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
        const body = (await res.json()) as { detail?: string };
        if (body && typeof body.detail === "string") detail = body.detail;
      } catch {
        // Ignore JSON parse errors; fall back to status text.
      }
      throw new Error(detail);
    }
    return (await res.json()) as AIGenerateResult;
  },
};
