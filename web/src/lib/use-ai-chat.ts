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

import { useCallback, useEffect, useRef, useState } from "react";

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
import type { DeviceType } from "./api";
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
  onStopped?: (unresolved: ToolCall[], reason: StopReason) => void;
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
  /**
   * Keep the approval card up until the server reports the call running.
   * An approve is not "done" when the request goes out: a rejected resume
   * must leave the decision pending, not pretend the tool ran.
   */
  keepApproval?: boolean;
}

/** Why a turn ended without a result for every call it started. */
export type StopReason = "stopped" | "error";

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
      // Every request starts a new assistant entry — a resume too, since the
      // server appends a fresh assistant message after the tool outcome.
      setMessages((prev) => [...prev, { role: "assistant", content: "", pending: true }]);

      const controller = new AbortController();
      abortRef.current = controller;
      setStatus("streaming");
      if (!options.keepApproval) setPendingApproval(null);
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
      // A call's outcome may belong to an earlier entry (the approved call
      // sits in the entry that proposed it), so results patch by id.
      const patchCall = (id: string, update: (c: ToolCallDisplay) => ToolCallDisplay) =>
        setMessages((prev) => patchCallById(prev, id, update));

      try {
        await streamChat(
          {
            messages: toWireMessages(history, options.resume?.tool_call_id),
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
              patch((m) => ({ ...m, status: { phase: s.phase, toolCallId: s.tool_call_id } }));
              if (s.phase === "tool_running" && s.tool_call_id) {
                // The server confirms a call is running. For an approved
                // call this is the only signal (no tool_call frame is
                // re-sent), so the card leaves "awaiting approval" here and
                // the call joins this turn's set — Stop must report it.
                const id = s.tool_call_id;
                if (!callsRef.current.has(id)) {
                  const known = findCall(history, id);
                  if (known) callsRef.current.set(id, known);
                }
                patchCall(id, (c) => (c.phase === "awaiting_approval" ? { ...c, phase: "running" } : c));
                setPendingApproval((p) => (p?.id === id ? null : p));
              }
              onStatus?.(s);
            },
            onToolCall: (call) => {
              callsRef.current.set(call.id, call);
              const display: ToolCallDisplay = {
                ...call,
                phase: "running",
                appliedSnapshot: computeAppliedSnapshot(call, runningSnapshot),
                deviceType: deviceTypeForCall(call, ctx.deviceType),
              };
              if (display.appliedSnapshot) runningSnapshot = display.appliedSnapshot;
              patch((m) => ({ ...m, toolCalls: [...(m.toolCalls ?? []), display] }));
              onToolCall?.(call);
            },
            onToolResult: (result) => {
              resolvedRef.current.add(result.id);
              patch((m) => ({ ...m, status: undefined }));
              patchCall(result.id, (c) => ({ ...c, result, phase: result.status as ToolPhase }));
              setPendingApproval((p) => (p?.id === result.id ? null : p));
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
                patchCall(id, (c) => ({ ...c, phase: "awaiting_approval" }));
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
        const stillRunning = new Set(unresolved.map((c) => c.id));
        setMessages((prev) => {
          const settled = patchLastAssistant(prev, (m) => ({ ...m, pending: false, status: undefined }));
          if (ended) return settled;
          return settled.map((m) =>
            m.role === "assistant" && m.toolCalls
              ? {
                  ...m,
                  toolCalls: m.toolCalls.map((c) =>
                    c.phase === "running" && stillRunning.has(c.id) ? { ...c, phase: "stopped" } : c,
                  ),
                }
              : m,
          );
        });
        // A fatal `error` frame (or a rejected resume) is not a Stop: the
        // caller may still refresh what a call could have changed, but it
        // must not tell the user they stopped anything.
        if (!ended && unresolved.length > 0) onStopped?.(unresolved, streamHadError ? "error" : "stopped");
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

  // The event handlers below read the latest transcript without
  // re-creating themselves on every streamed delta. The ref is written from
  // an effect, never during render (React Compiler rule).
  const messagesRef = useRef(messages);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const current = messagesRef.current;

      if (pendingElicitation) {
        // The composer is the answer channel while a question is pending.
        const id = pendingElicitation.id;
        const answer: ElicitationAnswer = { action: "accept", content: { answer: trimmed } };
        const next = recordAnswer(current, id, answer);
        setMessages(next);
        setPendingElicitation(null);
        void runStream(next, { resume: { tool_call_id: id, decision: "answer", answer } });
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
      if (decision === "deny") {
        const next = patchCallById(current, toolCallId, (c) => ({ ...c, phase: "denied" }));
        setMessages(next);
        setPendingApproval(null);
        void runStream(next, { resume: { tool_call_id: toolCallId, decision } });
        return;
      }
      // The card stays "awaiting approval" until the server says the call
      // is running (a status frame); a rejected resume leaves it pending.
      void runStream(current, { resume: { tool_call_id: toolCallId, decision }, keepApproval: true });
    },
    [runStream],
  );

  const answer = useCallback(
    (toolCallId: string, given: ElicitationAnswer) => {
      const next = recordAnswer(messagesRef.current, toolCallId, given);
      setMessages(next);
      setPendingElicitation(null);
      void runStream(next, { resume: { tool_call_id: toolCallId, decision: "answer", answer: given } });
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

/** Pure: update one tool call wherever it sits in the transcript. */
function patchCallById(
  messages: ChatMessage[],
  id: string,
  update: (c: ToolCallDisplay) => ToolCallDisplay,
): ChatMessage[] {
  return messages.map((m) =>
    m.role === "assistant" && m.toolCalls?.some((c) => c.id === id)
      ? { ...m, toolCalls: m.toolCalls.map((c) => (c.id === id ? update(c) : c)) }
      : m,
  );
}

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

/** The call with this id, wherever it sits in the transcript. */
export function findCall(history: ChatMessage[], id: string): ToolCallDisplay | undefined {
  for (let i = history.length - 1; i >= 0; i--) {
    const hit = history[i].toolCalls?.find((c) => c.id === id);
    if (hit) return hit;
  }
  return undefined;
}

/** Pure: the answer on the question's entry, and its ask_user call settled. */
function recordAnswer(history: ChatMessage[], toolCallId: string, given: ElicitationAnswer): ChatMessage[] {
  const withAnswer = history.map((m) =>
    m.role === "assistant" && m.elicitation?.id === toolCallId
      ? { ...m, elicitation: { ...m.elicitation, answer: given } }
      : m,
  );
  return patchCallById(withAnswer, toolCallId, (c) => ({ ...c, phase: "ok" }));
}

/** A create_page card previews at the size the page is created for. */
function deviceTypeForCall(call: ToolCall, fallback: DeviceType): DeviceType {
  if (call.name === "create_page") {
    const requested = (call.args as unknown as CreatePageArgs).device_type;
    if (typeof requested === "string") return requested;
  }
  return fallback;
}

/**
 * Pure: the structured transcript the server replays. Each assistant turn
 * carries its calls; each call that has an outcome (or was answered,
 * denied, or interrupted by Stop) is followed by a `tool` entry, so the
 * server can render the turn exactly as it did while running it.
 *
 * `awaitingToolCallId` is the call a `resume` on the same request decides.
 * The panel records the decision on its card before the request goes out,
 * so that call must stay unresolved here: the server rejects a resume for a
 * call the transcript already answers ("No tool call … is awaiting a
 * decision").
 */
export function toWireMessages(history: ChatMessage[], awaitingToolCallId?: string): WireMessage[] {
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
      if (c.id === awaitingToolCallId) continue; // the resume carries the decision
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
    // The editor's page is only the base when it is the page being updated;
    // an update to another page has nothing local to build on.
    const target = base?.id && base.id === a.page_id ? base : undefined;
    const template = a.template_lines ?? target?.template;
    if (!template) return undefined;
    return {
      ...(target?.id ? { id: target.id } : {}),
      name: a.name ?? target?.name ?? "",
      template,
      line_metadata: template.map((_, i) => target?.line_metadata?.[i] ?? { alignment: "left", wrap: false }),
    };
  }
  return undefined;
}
