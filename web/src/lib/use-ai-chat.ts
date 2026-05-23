// Chat state + streaming controller for the AI page chat panel.
//
// Owns the conversation array. Each `send()` posts the full history
// (plus a fresh `current_page` snapshot supplied by the caller) to
// /pages/ai/chat and forwards SSE events back into the in-flight
// assistant message.
//
// The hook is UI-framework-neutral — it doesn't render anything and
// doesn't know about the editor's form state. Callers wire the
// `onToolCall` callback to the editor's apply function.

import { useCallback, useRef, useState } from "react";

import { streamChat } from "./api-stream";
import type {
  ChatMessage,
  ChatTurnContext,
  CurrentPageSnapshot,
  ToolCall,
  ToolCallDisplay,
} from "./ai-chat-types";
import { applyPatchToSnapshot } from "./line-ops";

export interface UseAiChatOptions {
  /**
   * Called per turn to grab the freshest editor state. Returning
   * different `deviceType` between turns is supported — the backend
   * just adapts its layout constraints accordingly.
   */
  getTurnContext: () => ChatTurnContext;
  /** Fired as soon as a validated tool call arrives over SSE. */
  onToolCall: (call: ToolCall) => void;
  providerId?: string;
  model?: string;
}

export interface UseAiChatResult {
  messages: ChatMessage[];
  status: "idle" | "streaming" | "error";
  error: string | null;
  send: (text: string) => void;
  cancel: () => void;
  retryLast: () => void;
  reset: () => void;
}

export function useAiChat(opts: UseAiChatOptions): UseAiChatResult {
  const {
    getTurnContext,
    onToolCall,
    providerId,
    model,
  } = opts;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<"idle" | "streaming" | "error">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);

  // We keep the abort controller in a ref so cancel() works without
  // re-rendering, and so a stale render doesn't leak the controller.
  const abortRef = useRef<AbortController | null>(null);

  const runStream = useCallback(
    async (history: ChatMessage[]) => {
      // Append a placeholder assistant message that we'll mutate as
      // tokens arrive.
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "", pending: true },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;
      setStatus("streaming");
      setError(null);

      const wireMessages = history.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      let streamHadError = false;

      const appendToAssistant = (delta: string) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === "assistant") {
            next[next.length - 1] = {
              ...last,
              content: last.content + delta,
            };
          }
          return next;
        });
      };

      const attachToAssistant = (
        update: (m: ChatMessage) => ChatMessage,
      ) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === "assistant") {
            next[next.length - 1] = update(last);
          }
          return next;
        });
      };

      const ctx = getTurnContext();

      // Track the page state as the AI patches it across multiple
      // tool calls in a single turn. We start from the pre-call
      // snapshot and roll forward locally so each tool-call card can
      // render a static board preview without round-tripping the
      // editor's React state.
      let runningSnapshot: CurrentPageSnapshot | undefined = ctx.currentPage;

      try {
        await streamChat(
          {
            messages: wireMessages,
            device_type: ctx.deviceType,
            surface: ctx.surface,
            current_page: ctx.currentPage,
            available_pages: ctx.availablePages,
            installed_plugins: ctx.installedPlugins,
            available_schedules: ctx.availableSchedules,
            available_carousels: ctx.availableCarousels,
            registry_plugins: ctx.registryPlugins,
            provider_id: providerId,
            model,
          },
          {
            onText: appendToAssistant,
            onToolCall: (call) => {
              const display: ToolCallDisplay = {
                ...call,
                appliedSnapshot: computeAppliedSnapshot(call, runningSnapshot),
                deviceType: ctx.deviceType,
              };
              if (display.appliedSnapshot) {
                runningSnapshot = display.appliedSnapshot;
              }
              attachToAssistant((m) => ({
                ...m,
                toolCalls: [...(m.toolCalls ?? []), display],
              }));
              onToolCall(call);
            },
            onWarning: (msg) => {
              attachToAssistant((m) => ({
                ...m,
                warnings: [...(m.warnings ?? []), msg],
              }));
            },
            onError: (msg) => {
              streamHadError = true;
              setError(msg);
            },
          },
          controller.signal,
        );
      } finally {
        abortRef.current = null;
        attachToAssistant((m) => ({ ...m, pending: false }));
        setStatus(streamHadError ? "error" : "idle");
      }
    },
    [getTurnContext, onToolCall, providerId, model],
  );

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const userMsg: ChatMessage = { role: "user", content: trimmed };
      const next = [...messages, userMsg];
      setMessages(next);
      void runStream(next);
    },
    [runStream, messages],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const retryLast = useCallback(() => {
    // Walk back to the last user turn and resend from there.
    let lastUserIdx = -1;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        lastUserIdx = i;
        break;
      }
    }
    if (lastUserIdx === -1) return;
    const next = messages.slice(0, lastUserIdx + 1);
    setMessages(next);
    void runStream(next);
  }, [runStream, messages]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setStatus("idle");
    setError(null);
  }, []);

  return { messages, status, error, send, cancel, retryLast, reset };
}

/**
 * Pure: produce the page state *as it would render* after applying a
 * single tool call to a running snapshot. Used to attach a static
 * preview to each tool-call card in the chat thread.
 *
 * Returns `undefined` for ops that don't modify the page
 * (`suggest_variables`) or when there's no usable starting snapshot
 * (e.g. an `apply_patch` against an empty editor).
 */
function computeAppliedSnapshot(
  call: ToolCall,
  base: CurrentPageSnapshot | undefined,
): CurrentPageSnapshot | undefined {
  if (call.op === "replace_page") {
    return {
      name: call.args.name,
      template: call.args.template,
      line_metadata: call.args.line_metadata,
    };
  }
  if (call.op === "apply_patch") {
    if (!base) return undefined;
    const result = applyPatchToSnapshot(
      call.args.changes,
      base.template,
      base.line_metadata,
    );
    return {
      name: call.args.rename ?? base.name,
      template: result.template,
      line_metadata: result.line_metadata,
    };
  }
  return undefined;
}
