import type { ChatMessage, ToolCall } from "./ai-chat-types";
import type { ChatStatus } from "./use-ai-chat";

export type AiChatActivityState =
  | "idle"
  | "thinking"
  | "preparing"
  | "running"
  | "writing"
  | "approval"
  | "input"
  | "complete"
  | "error"
  | "stopped"
  | "paused"
  | "denied";

export interface AiChatActivity {
  state: AiChatActivityState;
  tool?: ToolCall;
}

/** Activity reflects the latest turn's observed events, never a predicted plan. */
export function deriveChatActivity(
  messages: ChatMessage[],
  status: ChatStatus,
  error?: string | null,
  pausedAtLimit = false,
): AiChatActivity {
  let start = messages.length;
  while (start > 0 && messages[start - 1].role === "assistant") start -= 1;
  const entries = messages.slice(start);
  const last = entries.at(-1);
  const calls = entries.flatMap((entry) => entry.toolCalls ?? []).filter((call) => call.name !== "ask_user");

  if (status === "awaiting_approval") return { state: "approval" };
  if (status === "awaiting_input") return { state: "input" };
  if (status === "error" || (error && status !== "streaming")) return { state: "error" };
  if (status === "streaming") {
    if (last?.draft) return { state: "preparing" };
    const running = calls.findLast((call) => call.phase === "running");
    if (running) return { state: "running", tool: running };
    if (last?.status?.phase === "tool_running") return { state: "running" };
    if (last?.status?.phase === "thinking") return { state: "thinking" };
    return { state: last?.content ? "writing" : "thinking" };
  }
  if (pausedAtLimit) return { state: "paused" };
  if (!last) return { state: "idle" };
  if (last.finishReason) return { state: last.finishReason };
  if (calls.some((call) => call.phase === "error" || call.phase === "blocked")) return { state: "error" };
  if (calls.some((call) => call.phase === "stopped")) return { state: "stopped" };
  if (calls.some((call) => call.phase === "denied")) return { state: "denied" };
  return { state: "complete" };
}

export function isActiveChatActivity(state: AiChatActivityState): boolean {
  return state === "thinking" || state === "preparing" || state === "running" || state === "writing";
}
