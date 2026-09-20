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
// "Approve and don't ask again in this chat" (#2021) is an approve that
// also sets a per-conversation flag; every later request of the
// conversation carries it as `approval.auto_approve_destructive`, and
// `reset()` (New chat) forgets it. The install-level Ask / Auto setting is
// the server's to read — it never travels in the request.
//
// The conversation is persisted (#2022): the first send mints a UUID, and
// every change to the transcript is autosaved under it through
// `PUT /ai/conversations/{id}` — debounced while a turn streams, at once
// when a turn ends or a decision is recorded. The id also sits in
// localStorage so a reload lands back in the same chat; `loadConversation`
// swaps a saved transcript in as the live one and `newConversation` starts
// a fresh id.
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
  SSEToolStreamingData,
  ToolCall,
  ToolCallDisplay,
  ToolPhase,
  ToolResult,
  UpdatePageArgs,
  WireMessage,
} from "./ai-chat-types";
import { api, ApiError, type ConversationUpsert, type DeviceType, type SavedConversation } from "./api";
import { streamChat } from "./api-stream";

/** Where the live conversation's id is remembered between page loads. */
export const CONVERSATION_ID_STORAGE_KEY = "fiestaboard:ai-conversation-id";

/** Debounce for the autosave while a turn is streaming. */
const AUTOSAVE_DEBOUNCE_MS = 1000;

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
  /** The model is writing a tool block; fired per `tool_streaming` frame. */
  onToolStreaming?: (draft: SSEToolStreamingData) => void;
  /** The turn finished with no decision pending. */
  onTurnComplete?: () => void;
  /** The user stopped the turn while these calls had no result yet. */
  onStopped?: (unresolved: ToolCall[], reason: StopReason) => void;
  /** A saved conversation became the live one (Continue, or the reload restore). */
  onConversationLoaded?: (conversation: SavedConversation) => void;
  /** An autosave landed on the server (the History list is stale now). */
  onSaved?: (conversationId: string) => void;
  /**
   * On mount, reopen the conversation whose id is in localStorage if the
   * server still has it. On by default; off for a panel that must start
   * empty.
   */
  restoreOnMount?: boolean;
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
  approve: (toolCallId: string, decision: ApprovalDecision, options?: ApproveOptions) => void;
  answer: (toolCallId: string, answer: ElicitationAnswer) => void;
  /** End the turn. A tool already running on the server still finishes. */
  stop: () => void;
  retryLast: () => void;
  /** True once the user chose "don't ask again" in this conversation. */
  autoApprove: boolean;
  /** Turn "don't ask again" back off; later destructive calls pause again. */
  disableAutoApprove: () => void;
  /** The id the transcript is saved under; null until the first send. */
  conversationId: string | null;
  /** Drop the live transcript and its id; the next send starts a new chat. */
  newConversation: () => void;
  /**
   * The live conversation's record is gone (deleted from History): keep
   * the transcript on screen but drop the id, so the next send continues
   * under a fresh one instead of resurrecting the deleted record.
   */
  forgetConversation: () => void;
  /**
   * Make a saved conversation the live one. Resolves with it, or null when
   * the server no longer has it (nothing changes then).
   */
  loadConversation: (id: string) => Promise<SavedConversation | null>;
}

export interface ApproveOptions {
  /**
   * Approve this call AND stop asking for the rest of the conversation:
   * every later request carries `approval.auto_approve_destructive`.
   * Meaningless with a `deny`.
   */
  autoApproveConversation?: boolean;
}

interface RunOptions {
  resume?: ResumePayload;
  /**
   * Keep the approval card up until the server reports the call running.
   * An approve is not "done" when the request goes out: a rejected resume
   * must leave the decision pending, not pretend the tool ran.
   */
  keepApproval?: boolean;
  /**
   * Arm "don't ask again" for this request and the rest of the conversation.
   * Set before the POST (the request itself carries the flag) and rolled
   * back if the stream does not reach `done` — a rejected resume or a
   * dropped connection approved nothing, so it must not leave the flag on.
   */
  autoApproveConversation?: boolean;
}

/** Why a turn ended without a result for every call it started. */
export type StopReason = "stopped" | "error";

export function useAiChat(opts: UseAiChatOptions): UseAiChatResult {
  const { getTurnContext, onToolCall, onToolResult, onAwaitingApproval, onElicitation, onStatus, onStopped } = opts;
  const { onConversationLoaded, onSaved, restoreOnMount = true, providerId, model } = opts;
  const { onToolStreaming, onTurnComplete } = opts;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [pendingApproval, setPendingApproval] = useState<ToolCall | null>(null);
  const [pendingElicitation, setPendingElicitation] = useState<Elicitation | null>(null);
  const [error, setError] = useState<string | null>(null);
  // "Don't ask again in this chat". State for the UI, a ref for the request
  // body: approve() sets both and re-POSTs in the same tick, before React
  // has re-rendered.
  const [autoApprove, setAutoApprove] = useState(false);
  const autoApproveRef = useRef(false);
  // The id the transcript is saved under. State for the UI, a ref so
  // send() can mint one and use it in the same tick.
  const [conversationId, setConversationId] = useState<string | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const adoptConversationId = useCallback((id: string | null) => {
    conversationIdRef.current = id;
    setConversationId(id);
    if (id) writeStoredConversationId(id);
    else clearStoredConversationId();
  }, []);

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
  // Autosave bookkeeping (see the Autosave section below): the next
  // transcript change is saved without the debounce when `saveAtOnceRef`
  // is set (a turn ended, a decision was recorded); the timer, the
  // coalesced payload and the in-order chain of PUTs.
  const saveAtOnceRef = useRef(false);
  const saveTimerRef = useRef<number | null>(null);
  const pendingSaveRef = useRef<{ id: string; body: ConversationUpsert } | null>(null);
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());
  // True while a saved transcript is being installed as the live one: that
  // messages change is a load, not an edit, and must not be saved back.
  const hydratingRef = useRef(false);
  const mountedRef = useRef(false);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const runStream = useCallback(
    async (history: ChatMessage[], options: RunOptions = {}) => {
      // Every request starts a new assistant entry — a resume too, since the
      // server appends a fresh assistant message after the tool outcome.
      setMessages((prev) => [...prev, { role: "assistant", content: "", pending: true }]);

      const controller = new AbortController();
      abortRef.current = controller;
      setStatus("streaming");
      if (options.autoApproveConversation) {
        autoApproveRef.current = true;
        setAutoApprove(true);
      }
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
            approval: autoApproveRef.current ? { auto_approve_destructive: true } : undefined,
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
            onToolStreaming: (draft) => {
              patch((m) => ({ ...m, draft }));
              onToolStreaming?.(draft);
            },
            onToolCall: (call) => {
              patch((m) => ({ ...m, draft: undefined }));
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
              patch((m) => ({ ...m, draft: undefined }));
              if (info.reason === "complete" || info.reason === "step_limit") onTurnComplete?.();
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
        // A stream superseded by loadConversation / newConversation (which
        // abort it and take the controller away) belongs to a conversation
        // that is no longer on screen: it must not settle, report or save
        // anything against the one that replaced it. Stop() aborts but
        // leaves the controller in place, so a stopped turn still settles.
        if (abortRef.current !== controller) return;
        abortRef.current = null;
        // Calls without a result when the stream ended (Stop, or a fatal
        // error) are reported so the caller can refresh what may have
        // changed anyway; the transcript renders them as interrupted.
        const unresolved = [...callsRef.current.values()].filter((c) => !resolvedRef.current.has(c.id));
        const stillRunning = new Set(unresolved.map((c) => c.id));
        // The turn is over: the settled transcript below is saved at once,
        // not after the streaming debounce.
        saveAtOnceRef.current = true;
        setMessages((prev) => {
          const settled = patchLastAssistant(prev, (m) => ({
            ...m,
            pending: false,
            status: undefined,
            draft: undefined,
          }));
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
        if (options.autoApproveConversation && !ended) {
          // The approval never happened; "don't ask again" goes with it.
          autoApproveRef.current = false;
          setAutoApprove(false);
        }
        // A turn that did not end with a decision pending is over for the
        // walkthrough too (a Stop or an error included).
        if (!ended) onTurnComplete?.();
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
      onToolStreaming,
      onTurnComplete,
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

  // -------------------------------------------------------------------------
  // Autosave. A change to the transcript (or to the approval flag) records
  // a pending payload; the debounce (or "at once" for a turn end and a
  // decision) hands it to a chain of PUTs that go out in order. The payload
  // is snapshotted when it joins the chain, so a save queued behind a slow
  // PUT survives a New chat in the meantime. A failed save is dropped
  // silently: autosave must never interrupt the chat, and the next change
  // retries with a fuller transcript anyway.
  // -------------------------------------------------------------------------
  const optsRef = useRef({ providerId, model, onSaved });
  useEffect(() => {
    optsRef.current = { providerId, model, onSaved };
  }, [providerId, model, onSaved]);

  const flushPendingSave = useCallback(() => {
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const pending = pendingSaveRef.current;
    pendingSaveRef.current = null;
    if (!pending) return;
    saveChainRef.current = saveChainRef.current.then(async () => {
      try {
        await api.saveConversation(pending.id, pending.body);
        optsRef.current.onSaved?.(pending.id);
      } catch {
        /* see above: never interrupt the chat over a failed autosave */
      }
    });
  }, []);

  const queueSave = useCallback(
    (atOnce: boolean, history: ChatMessage[] = messagesRef.current) => {
      const id = conversationIdRef.current;
      if (!id || history.length === 0) return;
      // Provider and model are left out (not nulled) while the panel has
      // none yet — /settings/ai may still be loading — so the server keeps
      // what an earlier save recorded.
      pendingSaveRef.current = {
        id,
        body: {
          provider_id: optsRef.current.providerId,
          model: optsRef.current.model,
          approval: autoApproveRef.current,
          messages: history,
        },
      };
      if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current);
      if (atOnce) {
        flushPendingSave();
        return;
      }
      saveTimerRef.current = window.setTimeout(flushPendingSave, AUTOSAVE_DEBOUNCE_MS);
    },
    [flushPendingSave],
  );

  useEffect(() => {
    if (hydratingRef.current) {
      // This change installed a saved transcript; there is nothing new to save.
      hydratingRef.current = false;
      return;
    }
    const atOnce = saveAtOnceRef.current;
    saveAtOnceRef.current = false;
    queueSave(atOnce, messages);
  }, [messages, queueSave]);

  useEffect(() => {
    return () => {
      // Unmount: send whatever is still waiting rather than lose it.
      flushPendingSave();
    };
  }, [flushPendingSave]);

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const current = messagesRef.current;
      if (!conversationIdRef.current) adoptConversationId(newConversationId());

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
    [runStream, pendingApproval, pendingElicitation, adoptConversationId],
  );

  const approve = useCallback(
    (toolCallId: string, decision: ApprovalDecision, options: ApproveOptions = {}) => {
      const current = messagesRef.current;
      // A decision is worth keeping even if the resume never lands.
      saveAtOnceRef.current = true;
      if (decision === "deny") {
        const next = patchCallById(current, toolCallId, (c) => ({ ...c, phase: "denied" }));
        setMessages(next);
        setPendingApproval(null);
        void runStream(next, { resume: { tool_call_id: toolCallId, decision } });
        return;
      }
      // The card stays "awaiting approval" until the server says the call
      // is running (a status frame); a rejected resume leaves it pending.
      void runStream(current, {
        resume: { tool_call_id: toolCallId, decision },
        keepApproval: true,
        autoApproveConversation: options.autoApproveConversation === true,
      });
    },
    [runStream],
  );

  const answer = useCallback(
    (toolCallId: string, given: ElicitationAnswer) => {
      saveAtOnceRef.current = true;
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

  const disableAutoApprove = useCallback(() => {
    autoApproveRef.current = false;
    setAutoApprove(false);
    // The flag is part of the record: a reload or Continue must not bring
    // "don't ask again" back after the user turned it off.
    queueSave(true);
  }, [queueSave]);

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

  const newConversation = useCallback(() => {
    // Take the controller away so the old turn, if one is running, settles
    // nothing against the empty chat (see runStream's finally).
    abortRef.current?.abort();
    abortRef.current = null;
    // The old chat's last save goes out before the switch, debounce or not.
    flushPendingSave();
    setMessages([]);
    setStatus("idle");
    setPendingApproval(null);
    setPendingElicitation(null);
    setError(null);
    // "Don't ask again" was for that conversation; a new chat asks again.
    autoApproveRef.current = false;
    setAutoApprove(false);
    adoptConversationId(null);
  }, [adoptConversationId, flushPendingSave]);

  const forgetConversation = useCallback(() => {
    // The record is gone; a save still waiting for it would only bring it
    // back. The transcript stays, and the next send mints a fresh id.
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    pendingSaveRef.current = null;
    adoptConversationId(null);
  }, [adoptConversationId]);

  // -------------------------------------------------------------------------
  // Loading a saved conversation, and reopening the last one on mount.
  // -------------------------------------------------------------------------
  const applyLoaded = useCallback(
    (conversation: SavedConversation) => {
      // Take the controller away: a turn still streaming belongs to the
      // chat being replaced and must settle nothing against this one.
      abortRef.current?.abort();
      abortRef.current = null;
      const history = settleSavedTranscript(conversation.messages);
      const last = history[history.length - 1];
      const awaiting = last?.role === "assistant" ? last.toolCalls?.find((c) => c.phase === "awaiting_approval") : null;
      const question =
        last?.role === "assistant" && last.elicitation && !last.elicitation.answer ? last.elicitation : null;
      // Installing the transcript is not an edit: the messages effect below
      // skips the save this change would otherwise queue.
      hydratingRef.current = true;
      setMessages(history);
      setStatus("idle");
      setError(null);
      setPendingApproval(awaiting ?? null);
      setPendingElicitation(question ?? null);
      autoApproveRef.current = conversation.approval;
      setAutoApprove(conversation.approval);
      adoptConversationId(conversation.id);
      onConversationLoaded?.(conversation);
    },
    [adoptConversationId, onConversationLoaded],
  );

  const loadConversation = useCallback(
    async (id: string): Promise<SavedConversation | null> => {
      let conversation: SavedConversation;
      try {
        conversation = await api.getConversation(id);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
      if (!mountedRef.current) return null;
      applyLoaded(conversation);
      return conversation;
    },
    [applyLoaded],
  );

  const applyLoadedRef = useRef(applyLoaded);
  useEffect(() => {
    applyLoadedRef.current = applyLoaded;
  }, [applyLoaded]);

  useEffect(() => {
    if (!restoreOnMount) return;
    const stored = readStoredConversationId();
    if (!stored) return;
    let cancelled = false;
    // A send that happens while this GET is in flight has already minted
    // its own id and is streaming; the restore then yields to it, and the
    // stored id (already overwritten by the new one) is left alone.
    const superseded = () => cancelled || conversationIdRef.current !== null || abortRef.current !== null;
    void api.getConversation(stored).then(
      (conversation) => {
        if (superseded()) return;
        applyLoadedRef.current(conversation);
      },
      (err: unknown) => {
        if (err instanceof ApiError && err.status === 404 && !superseded()) clearStoredConversationId();
        /* anything else: the server is unreachable right now; keep the id for next time */
      },
    );
    return () => {
      cancelled = true;
    };
  }, [restoreOnMount]);

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
    autoApprove,
    disableAutoApprove,
    conversationId,
    newConversation,
    loadConversation,
    forgetConversation,
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

// ---------------------------------------------------------------------------
// Persistence helpers
// ---------------------------------------------------------------------------

/** A v4 UUID; `crypto.randomUUID` where it exists, a manual v4 otherwise. */
export function newConversationId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  const bytes = new Uint8Array(16);
  if (c && typeof c.getRandomValues === "function") c.getRandomValues(bytes);
  else for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// localStorage is a per-browser convenience, not the record: every read and
// write is guarded, and a missing or unreadable value means "no live chat".
function readStoredConversationId(): string | null {
  try {
    return localStorage.getItem(CONVERSATION_ID_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredConversationId(id: string): void {
  try {
    localStorage.setItem(CONVERSATION_ID_STORAGE_KEY, id);
  } catch {
    /* storage may be unavailable */
  }
}

function clearStoredConversationId(): void {
  try {
    localStorage.removeItem(CONVERSATION_ID_STORAGE_KEY);
  } catch {
    /* storage may be unavailable */
  }
}

/**
 * Pure: a saved transcript made safe to show as the live one. A save can
 * land mid-turn (the debounce, or a reload while streaming), so an entry
 * may still say `pending` and a call may still be `running`; nothing is
 * coming for them any more, so they are settled — the same rendering as a
 * turn the user stopped. A call awaiting approval and an unanswered
 * question are kept as they are: the resume that answers them still works.
 */
export function settleSavedTranscript(saved: ChatMessage[]): ChatMessage[] {
  return saved.map((m) => {
    if (m.role !== "assistant") return { role: "user", content: m.content };
    // `draft` goes with `status`: a turn cut short mid-block was saved with
    // the block on it, and a restored transcript must not show a call
    // being prepared that will never arrive.
    const { status: _status, draft: _draft, ...rest } = m;
    return {
      ...rest,
      pending: false,
      toolCalls: m.toolCalls?.map((c) => (c.phase === "running" ? { ...c, phase: "stopped" } : c)),
    };
  });
}
