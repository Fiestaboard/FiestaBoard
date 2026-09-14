// Chat state + streaming controller for the AI chat panel.
//
// Owns the conversation array. Each `send()` posts the full transcript
// (plus a fresh context snapshot supplied by the caller) to /pages/ai/chat
// and forwards SSE events into the in-flight assistant message. The server
// runs the whole turn — model calls, tool executions — and pauses only for
// the two things a person has to answer: approving a destructive tool, and
// replying to a question. Both come back through `approve()` / `answer()`,
// which re-POST the transcript with a `resume` decision and keep appending
// to the same assistant message.
//
// The hook is UI-framework-neutral — it doesn't render anything and
// doesn't execute tools. Callers observe what the server is doing through
// the `onToolCall` / `onToolResult` callbacks.

import { useCallback, useRef, useState } from "react";

import type {
  ApprovalDecision,
  ChatMessage,
  ChatTurnContext,
  CreatePageArgs,
  CurrentPageSnapshot,
  Elicitation,
  ElicitationAnswer,
  ResumePayload,
  SSEStatusData,
  ToolCall,
  ToolCallDisplay,
  ToolPhase,
  ToolResult,
  UpdatePageArgs,
  WireMessage,
} from "./ai-chat-types";
import { streamChat } from "./api-stream";

export type ChatStatus = "idle" | "streaming" | "awaiting_approval" | "awaiting_input" | "error";

export interface UseAiChatOptions {
  /**
   * Called per turn to grab the freshest editor state. Returning
   * different `deviceType` between turns is supported — the backend
   * just adapts its layout constraints accordingly.
   */
  getTurnContext: () => ChatTurnContext;
  /** A validated call arrived; the server is about to run it (or is waiting on the user). */
  onToolCall?: (call: ToolCall) => void;
  /** The call finished (or was denied). */
  onToolResult?: (result: ToolResult, call: ToolCall) => void;
  /** A destructive call waits on the user. */
  onAwaitingApproval?: (call: ToolCall) => void;
  /** The assistant asked the user a question. */
  onElicitation?: (elicitation: Elicitation) => void;
  onStatus?: (status: SSEStatusData) => void;
  /** The user stopped the turn while these calls had no result yet. */
  onStopped?: (unresolved: ToolCall[]) => void;
  providerId?: string;
  model?: string;
}

export interface UseAiChatResult {
  messages: ChatMessage[];
  status: ChatStatus;
  /** The destructive call the turn is paused on, if any. */
  pendingApproval: ToolCall | null;
  /** The question the turn is paused on, if any. */
  pendingElicitation: Elicitation | null;
  error: string | null;
  /**
   * Send a message. While a question is pending, the text is the answer.
   * While an approval is pending, the call is denied and the text sent.
   */
  send: (text: string) => void;
  approve: (toolCallId: string, decision: ApprovalDecision) => void;
  answer: (toolCallId: string, answer: ElicitationAnswer) => void;
  /** End the turn. A tool already running on the server still finishes. */
  stop: () => void;
  retryLast: () => void;
  reset: () => void;
}

interface RunOptions {
  resume?: ResumePayload;
  /** Keep appending to the current assistant message instead of starting one. */
  continueAssistant?: boolean;
}

export function useAiChat(opts: UseAiChatOptions): UseAiChatResult {
  const { getTurnContext, onToolCall, onToolResult, onAwaitingApproval, onElicitation, onStatus, onStopped } = opts;
  const { providerId, model } = opts;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [pendingApproval, setPendingApproval] = useState<ToolCall | null>(null);
  const [pendingElicitation, setPendingElicitation] = useState<Elicitation | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The abort controller lives in a ref so stop() works without a
  // re-render, and so a stale render doesn't leak the controller.
  const abortRef = useRef<AbortController | null>(null);
  // The calls of the in-flight turn, by id — read from handlers without
  // waiting for React state to catch up.
  const callsRef = useRef<Map<string, ToolCall>>(new Map());
  const resolvedRef = useRef<Set<string>>(new Set());
  // The question the server asked in this turn; `done{awaiting_input}`
  // arrives right after the elicitation frame and needs it without waiting
  // for React state to catch up.
  const elicitationRef = useRef<Elicitation | null>(null);

  const runStream = useCallback(
    async (history: ChatMessage[], options: RunOptions = {}) => {
      if (!options.continueAssistant) {
        setMessages((prev) => [...prev, { role: "assistant", content: "", pending: true }]);
      } else {
        setMessages((prev) => patchLastAssistant(prev, (m) => ({ ...m, pending: true })));
      }

      const controller = new AbortController();
      abortRef.current = controller;
      setStatus("streaming");
      setPendingApproval(null);
      setPendingElicitation(null);
      setError(null);
      callsRef.current = new Map();
      resolvedRef.current = new Set();
      elicitationRef.current = null;

      const ctx = getTurnContext();
      let streamHadError = false;
      let ended = false;
      // Track the page state as the AI changes it across the turn so each
      // page tool's card can render a board preview locally.
      let runningSnapshot: CurrentPageSnapshot | undefined = ctx.currentPage;

      const patch = (update: (m: ChatMessage) => ChatMessage) =>
        setMessages((prev) => patchLastAssistant(prev, update));

      try {
        await streamChat(
          {
            messages: toWireMessages(history),
            resume: options.resume,
            device_type: ctx.deviceType,
            surface: ctx.surface,
            current_page: ctx.currentPage,
            available_pages: ctx.availablePages,
            installed_plugins: ctx.installedPlugins,
            available_schedules: ctx.availableSchedules,
            available_collections: ctx.availableCollections,
            registry_plugins: ctx.registryPlugins,
            provider_id: providerId,
            model,
          },
          {
            onText: (delta) => patch((m) => ({ ...m, content: m.content + delta })),
            onStatus: (s) => {
              patch((m) => ({ ...m, statusMessage: s.message }));
              onStatus?.(s);
            },
            onToolCall: (call) => {
              callsRef.current.set(call.id, call);
              const display: ToolCallDisplay = {
                ...call,
                phase: "running",
                appliedSnapshot: computeAppliedSnapshot(call, runningSnapshot),
                deviceType: ctx.deviceType,
              };
              if (display.appliedSnapshot) runningSnapshot = display.appliedSnapshot;
              patch((m) => ({ ...m, toolCalls: [...(m.toolCalls ?? []), display] }));
              onToolCall?.(call);
            },
            onToolResult: (result) => {
              resolvedRef.current.add(result.id);
              patch((m) => ({
                ...m,
                statusMessage: undefined,
                toolCalls: (m.toolCalls ?? []).map((c) =>
                  c.id === result.id ? { ...c, result, phase: result.status as ToolPhase } : c,
                ),
              }));
              const call = callsRef.current.get(result.id) ?? findCall(history, result.id);
              if (call) onToolResult?.(result, call);
            },
            onElicitation: (elicitation) => {
              elicitationRef.current = elicitation;
              patch((m) => ({ ...m, elicitation }));
            },
            onWarning: (msg) => patch((m) => ({ ...m, warnings: [...(m.warnings ?? []), msg] })),
            onError: (msg) => {
              streamHadError = true;
              setError(msg);
            },
            onDone: (info) => {
              ended = true;
              if (info.reason === "awaiting_approval" && info.pending_tool_call_id) {
                const id = info.pending_tool_call_id;
                const call = callsRef.current.get(id);
                patch((m) => ({
                  ...m,
                  toolCalls: (m.toolCalls ?? []).map((c) => (c.id === id ? { ...c, phase: "awaiting_approval" } : c)),
                }));
                if (call) {
                  setPendingApproval(call);
                  onAwaitingApproval?.(call);
                }
              } else if (info.reason === "awaiting_input" && info.pending_tool_call_id) {
                const el = elicitationRef.current;
                if (el && el.id === info.pending_tool_call_id) {
                  setPendingElicitation(el);
                  onElicitation?.(el);
                }
              }
            },
          },
          controller.signal,
        );
      } finally {
        abortRef.current = null;
        // Calls without a result when the stream ended (Stop, or a fatal
        // error) are reported so the caller can refresh what may have
        // changed anyway; the transcript renders them as interrupted.
        const unresolved = [...callsRef.current.values()].filter((c) => !resolvedRef.current.has(c.id));
        setMessages((prev) =>
          patchLastAssistant(prev, (m) => ({
            ...m,
            pending: false,
            statusMessage: undefined,
            toolCalls: (m.toolCalls ?? []).map((c) =>
              c.phase === "running" && !ended ? { ...c, phase: "stopped" } : c,
            ),
          })),
        );
        if (!ended && unresolved.length > 0) onStopped?.(unresolved);
        setStatus((current) => {
          if (streamHadError) return "error";
          if (current === "streaming") return "idle";
          return current;
        });
      }
    },
    [
      getTurnContext,
      onToolCall,
      onToolResult,
      onAwaitingApproval,
      onElicitation,
      onStatus,
      onStopped,
      providerId,
      model,
    ],
  );

  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const current = messagesRef.current;

      if (pendingElicitation) {
        // The composer is the answer channel while a question is pending.
        const id = pendingElicitation.id;
        const answer: ElicitationAnswer = { action: "accept", content: { answer: trimmed } };
        const next = patchLastAssistant(current, (m) =>
          m.elicitation ? { ...m, elicitation: { ...m.elicitation, answer } } : m,
        );
        setMessages(next);
        setPendingElicitation(null);
        void runStream(next, { resume: { tool_call_id: id, decision: "answer", answer }, continueAssistant: true });
        return;
      }

      const userMsg: ChatMessage = { role: "user", content: trimmed };
      const next = [...current, userMsg];
      setMessages(next);
      if (pendingApproval) {
        // Stop-then-type: the pending call is denied and the new prompt
        // goes with it in the same request.
        const denied = patchLastAssistant(next, (m) => ({
          ...m,
          toolCalls: (m.toolCalls ?? []).map((c) => (c.id === pendingApproval.id ? { ...c, phase: "denied" } : c)),
        }));
        setMessages(denied);
        setPendingApproval(null);
        void runStream(denied, { resume: { tool_call_id: pendingApproval.id, decision: "deny" } });
        return;
      }
      void runStream(next);
    },
    [runStream, pendingApproval, pendingElicitation],
  );

  const approve = useCallback(
    (toolCallId: string, decision: ApprovalDecision) => {
      const current = messagesRef.current;
      const next = patchLastAssistant(current, (m) => ({
        ...m,
        toolCalls: (m.toolCalls ?? []).map((c) =>
          c.id === toolCallId ? { ...c, phase: decision === "approve" ? "running" : "denied" } : c,
        ),
      }));
      setMessages(next);
      setPendingApproval(null);
      void runStream(next, { resume: { tool_call_id: toolCallId, decision }, continueAssistant: true });
    },
    [runStream],
  );

  const answer = useCallback(
    (toolCallId: string, given: ElicitationAnswer) => {
      const current = messagesRef.current;
      const next = patchLastAssistant(current, (m) =>
        m.elicitation ? { ...m, elicitation: { ...m.elicitation, answer: given } } : m,
      );
      setMessages(next);
      setPendingElicitation(null);
      void runStream(next, {
        resume: { tool_call_id: toolCallId, decision: "answer", answer: given },
        continueAssistant: true,
      });
    },
    [runStream],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const retryLast = useCallback(() => {
    const current = messagesRef.current;
    let lastUserIdx = -1;
    for (let i = current.length - 1; i >= 0; i--) {
      if (current[i].role === "user") {
        lastUserIdx = i;
        break;
      }
    }
    if (lastUserIdx === -1) return;
    const next = current.slice(0, lastUserIdx + 1);
    setMessages(next);
    setPendingApproval(null);
    setPendingElicitation(null);
    void runStream(next);
  }, [runStream]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setStatus("idle");
    setPendingApproval(null);
    setPendingElicitation(null);
    setError(null);
  }, []);

  // A pause is derived, not stored: the stream's own bookkeeping lands on
  // "idle" when it closes, and the pending call/question says what the turn
  // is actually waiting on.
  const paused = pendingApproval ? "awaiting_approval" : pendingElicitation ? "awaiting_input" : null;
  const effectiveStatus: ChatStatus = status === "idle" && paused ? paused : status;

  return {
    messages,
    status: effectiveStatus,
    pendingApproval,
    pendingElicitation,
    error,
    send,
    approve,
    answer,
    stop,
    retryLast,
    reset,
  };
}

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function patchLastAssistant(list: ChatMessage[], update: (m: ChatMessage) => ChatMessage): ChatMessage[] {
  const next = [...list];
  for (let i = next.length - 1; i >= 0; i--) {
    if (next[i].role === "assistant") {
      next[i] = update(next[i]);
      return next;
    }
  }
  return next;
}

function findCall(history: ChatMessage[], id: string): ToolCall | undefined {
  for (const m of history) {
    const hit = m.toolCalls?.find((c) => c.id === id);
    if (hit) return hit;
  }
  return undefined;
}

/**
 * Pure: the structured transcript the server replays. Each assistant turn
 * carries its calls; each call that has an outcome (or was answered,
 * denied, or interrupted by Stop) is followed by a `tool` entry, so the
 * server can render the turn exactly as it did while running it.
 */
export function toWireMessages(history: ChatMessage[]): WireMessage[] {
  const wire: WireMessage[] = [];
  for (const m of history) {
    if (m.role === "user") {
      wire.push({ role: "user", content: m.content });
      continue;
    }
    const calls = m.toolCalls ?? [];
    wire.push({
      role: "assistant",
      content: m.content,
      tool_calls: calls.length ? calls.map((c) => ({ id: c.id, name: c.name, args: c.args })) : undefined,
    });
    for (const c of calls) {
      if (c.name === "ask_user") {
        if (m.elicitation?.answer) {
          wire.push({
            role: "tool",
            tool_call_id: c.id,
            name: c.name,
            status: "answered",
            result: answerResult(m.elicitation.answer),
          });
        }
        continue;
      }
      if (c.phase === "running" || c.phase === "awaiting_approval") continue; // still pending — the resume carries it
      if (c.phase === "stopped") {
        wire.push({ role: "tool", tool_call_id: c.id, name: c.name, status: "interrupted", result: null });
        continue;
      }
      if (c.phase === "denied") {
        wire.push({ role: "tool", tool_call_id: c.id, name: c.name, status: "denied", result: null });
        continue;
      }
      if (c.result) {
        wire.push({
          role: "tool",
          tool_call_id: c.id,
          name: c.name,
          status: c.result.status,
          result: c.result.status === "error" ? { error: c.result.error } : c.result.result,
        });
      }
    }
  }
  return wire;
}

function answerResult(answer: ElicitationAnswer): unknown {
  if (answer.action === "accept") return { answer: answer.content.answer ?? answer.content };
  return { answer: answer.action === "decline" ? "(declined)" : "(cancelled)" };
}

/**
 * Pure: the page as it would render after a page tool, so its card can show
 * a board preview before (and regardless of) the server's result.
 */
export function computeAppliedSnapshot(
  call: Pick<ToolCall, "name" | "args">,
  base: CurrentPageSnapshot | undefined,
): CurrentPageSnapshot | undefined {
  if (call.name === "create_page") {
    const a = call.args as unknown as CreatePageArgs;
    if (!Array.isArray(a.template_lines)) return undefined;
    return {
      name: a.name ?? "",
      template: a.template_lines,
      line_metadata: a.template_lines.map(() => ({ alignment: "left", wrap: false })),
    };
  }
  if (call.name === "update_page") {
    const a = call.args as unknown as UpdatePageArgs;
    const template = a.template_lines ?? base?.template;
    if (!template) return undefined;
    return {
      name: a.name ?? base?.name ?? "",
      template,
      line_metadata: template.map((_, i) => base?.line_metadata?.[i] ?? { alignment: "left", wrap: false }),
    };
  }
  return undefined;
}
