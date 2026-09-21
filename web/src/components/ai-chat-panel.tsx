"use client";

import {
  Alert,
  AlertDescription,
  Box,
  Button,
  Card,
  Conversation,
  ConversationContent,
  ConversationScrollButton,
  Flex,
  Kbd,
  Label,
  Popover,
  PopoverContent,
  PopoverTrigger,
  PromptInput,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputToolbar,
  PromptInputTools,
  SegmentedControl,
  SegmentedControlItem,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Suggestion,
  Suggestions,
  Text,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft, History, RotateCcw, SlidersHorizontal, Sparkles, SquarePen, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { AiConversationReview, AiHistoryList, CONVERSATIONS_QUERY_KEY } from "@/components/ai-chat-history";
import { groupTurns, TranscriptTurns } from "@/components/ai-chat-transcript";
import { AiStepTimeline } from "@/components/ai-step-timeline";
import { useElementWidth } from "@/hooks/use-element-width";
import { useTranslations } from "@/i18n/translations";
import type {
  ApprovalDecision,
  ChatTurnContext,
  Elicitation,
  ElicitationAnswer,
  SSEStatusData,
  SSEToolStreamingData,
  ToolCall,
  ToolResult,
} from "@/lib/ai-chat-types";
import { type AiApprovalMode, type AISettings, api, type SavedConversation } from "@/lib/api";
import { type StopReason, useAiChat } from "@/lib/use-ai-chat";

export { groupTurns } from "@/components/ai-chat-transcript";

/**
 * Panel width below which the Enter/Shift+Enter hint gives up its place in
 * the composer toolbar and rides on the Send button instead.
 *
 * The row now carries three things, not five: the settings pill, the hint and
 * Send. Measured against the real controls — pill ~120px (it truncates), hint
 * ~180, Send ~36, ~14 of gaps and 40 of padding — the hint needs about 390px,
 * so 440 is that with a margin rather than a number tuned to the pixel. It
 * used to be 560, when the row also held a segmented control and two selects.
 *
 * Still above the drawer's 384px default, and deliberately: below this the
 * hint becomes the Send button's `title`, which says the same thing without
 * competing for the row.
 */
export const COMPOSER_HINT_WIDTH = 440;

export interface AiChatPanelProps {
  /** Per-turn context (device type, current page snapshot, what exists). */
  getTurnContext: () => ChatTurnContext;
  /** The server is about to run (or is waiting on the user for) this call. */
  onToolCall?: (call: ToolCall) => void;
  /** The call finished. The drawer invalidates caches and toasts here. */
  onToolResult?: (result: ToolResult, call: ToolCall) => void;
  onAwaitingApproval?: (call: ToolCall) => void;
  onElicitation?: (elicitation: Elicitation) => void;
  onStatus?: (status: SSEStatusData) => void;
  /** The model is writing a tool block; the walkthrough can start moving. */
  onToolStreaming?: (draft: SSEToolStreamingData) => void;
  /** The turn ended with nothing pending. */
  onTurnComplete?: () => void;
  /** A saved conversation replaced the live one; the walkthrough is over. */
  onConversationLoaded?: () => void;
  /** The user stopped the turn with these calls still running server-side. */
  onStopped?: (unresolved: ToolCall[], reason: StopReason) => void;
  /**
   * The drawer's spotlight shows Stop and Approve/Deny next to the control
   * being changed; this ref lets those buttons reach the conversation.
   */
  controllerRef?: React.MutableRefObject<AiChatController | null>;
  /** Close button hides the panel without losing the existing layout. */
  onClose: () => void;
}

/**
 * What the panel body shows. The live chat is the default; History is the
 * list of saved conversations (#2022) and Review is one of them opened
 * read-only, from which Continue returns to the chat with it loaded.
 */
type PanelMode = { kind: "chat" } | { kind: "history" } | { kind: "review"; id: string; title: string | null };

/**
 * The drawer's spotlight shows Stop and Approve/Deny beside the control being
 * changed; this is how those buttons reach the conversation.
 */
export interface AiChatController {
  approve: (toolCallId: string, decision: ApprovalDecision) => void;
  answer: (toolCallId: string, answer: ElicitationAnswer) => void;
  stop: () => void;
}

export function AiChatPanel({
  getTurnContext,
  onToolCall,
  onToolResult,
  onAwaitingApproval,
  onElicitation,
  onStatus,
  onToolStreaming,
  onTurnComplete,
  onConversationLoaded,
  onStopped,
  onClose,
  controllerRef,
}: AiChatPanelProps) {
  const t = useTranslations("aiChatPanel");
  // The panel measures itself: its width is the drawer's choice, not the
  // viewport's, so a media query would answer the wrong question.
  const panelRef = useRef<HTMLDivElement>(null);
  const panelWidth = useElementWidth(panelRef);
  const showSendHint = panelWidth >= COMPOSER_HINT_WIDTH;
  const [providerId, setProviderId] = useState<string>("");
  const [model, setModel] = useState<string>("");
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<PanelMode>({ kind: "chat" });

  const queryClient = useQueryClient();
  const { data: settings } = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: () => api.getAiSettings(),
  });

  // Ask / Auto is the install's setting (PUT /settings/ai), read and written
  // through the same query the Settings page uses. Optimistic while the PUT
  // is in flight so the pill moves on click, not on the round trip.
  // The one-line explanation of Auto, shown the first time it is saved from
  // this panel and taken down again when the user goes back to Ask. Both
  // commit on the PUT's success: a failed save shows no note.
  const [autoNote, setAutoNote] = useState(false);
  const autoNoteSeenRef = useRef(false);
  const modeMutation = useMutation({
    mutationFn: (approval_mode: AiApprovalMode) => api.updateAiSettings({ approval_mode }),
    onSuccess: (saved, requested) => {
      queryClient.setQueryData(["ai-settings"], saved);
      if (requested === "auto") {
        if (!autoNoteSeenRef.current) {
          autoNoteSeenRef.current = true;
          setAutoNote(true);
        }
      } else {
        setAutoNote(false);
      }
    },
    onError: (err: Error) => toast.error(err.message),
  });
  const { mutate: setApprovalMode } = modeMutation;
  const approvalMode: AiApprovalMode =
    modeMutation.isPending && modeMutation.variables ? modeMutation.variables : (settings?.approval_mode ?? "ask");

  const providers = settings?.providers ?? [];
  const selectedProvider =
    providers.find((p) => p.id === providerId) ??
    providers.find((p) => p.id === settings?.default_provider_id) ??
    providers[0];
  const effectiveProviderId = selectedProvider?.id ?? "";
  const availableModels = selectedProvider?.models ?? [];
  const effectiveModel =
    model && availableModels.includes(model) ? model : (selectedProvider?.default_model ?? availableModels[0] ?? "");

  const aiDisabled = settings ? !settings.enabled : false;
  const noProviders = providers.length === 0;
  const noModels = !!selectedProvider && !effectiveModel;
  const blocked = aiDisabled || noProviders || noModels;

  // A saved conversation carries the provider and model it was had with;
  // continuing it picks them back up (a provider that has since gone falls
  // through to the default above).
  const handleConversationLoaded = useCallback(
    (conversation: SavedConversation) => {
      setProviderId(conversation.provider_id ?? "");
      setModel(conversation.model ?? "");
      onConversationLoaded?.();
    },
    [onConversationLoaded],
  );
  // Every autosave makes the History list and the open review stale; the
  // app's query staleTime would otherwise show a minute-old list.
  const handleSaved = useCallback(
    () => void queryClient.invalidateQueries({ queryKey: CONVERSATIONS_QUERY_KEY }),
    [queryClient],
  );

  const {
    messages,
    status,
    pendingApproval,
    pendingElicitation,
    error,
    send,
    approve,
    answer,
    stop,
    retryLast,
    pausedAtLimit,
    continueTurn,
    autoApprove,
    disableAutoApprove,
    conversationId,
    newConversation,
    loadConversation,
    forgetConversation,
  } = useAiChat({
    getTurnContext,
    onToolCall,
    onToolResult,
    onAwaitingApproval,
    onElicitation,
    onStatus,
    onToolStreaming,
    onTurnComplete,
    onStopped,
    onConversationLoaded: handleConversationLoaded,
    onSaved: handleSaved,
    providerId: effectiveProviderId || undefined,
    model: effectiveModel || undefined,
  });

  // Slot-ref pattern: keep the drawer's ref pointed at the latest controller.
  useEffect(() => {
    if (controllerRef) controllerRef.current = { approve, answer, stop };
  }, [controllerRef, approve, answer, stop]);

  const streaming = status === "streaming";
  const composerStatus = streaming ? "streaming" : status === "error" ? "error" : "ready";
  // History hides the live transcript, so it waits while a turn is running
  // or paused on a card only the live chat can answer.
  const turnBusy = streaming || pendingApproval !== null || pendingElicitation !== null;

  // What the pill shows: "don't ask again" reads as Auto for this chat even
  // while the install stays on Ask. Choosing Ask turns the conversation
  // flag off (and, if the install is in Auto, saves Ask); choosing Auto
  // saves the install setting.
  const effectiveMode: AiApprovalMode = autoApprove ? "auto" : approvalMode;
  // Not claimed until the install setting is known: before the GET resolves
  // the fallback "ask" would flash the caption for an install that is in Auto.
  const autoForThisChatOnly = autoApprove && settings !== undefined && approvalMode === "ask";
  const handleModeChange = useCallback(
    (value: string) => {
      const next: AiApprovalMode = value === "auto" ? "auto" : "ask";
      if (next === "ask") {
        if (autoApprove) disableAutoApprove();
        if (approvalMode !== "ask") setApprovalMode("ask");
        return;
      }
      if (approvalMode !== "auto") setApprovalMode("auto");
    },
    [approvalMode, autoApprove, disableAutoApprove, setApprovalMode],
  );

  // Consecutive assistant entries (one per model call; a resume starts a
  // new one) read as one turn on screen.
  const turns = useMemo(() => groupTurns(messages), [messages]);
  const lastTurn = turns[turns.length - 1];
  const currentTurn = lastTurn?.role === "assistant" ? lastTurn : null;
  const lastEntry = currentTurn?.entries[currentTurn.entries.length - 1];

  const handleSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!draft.trim() || blocked || streaming) return;
      send(draft);
      setDraft("");
    },
    [draft, blocked, streaming, send],
  );

  const handleContinue = useCallback(
    (id: string) => {
      void loadConversation(id).then(
        (loaded) => {
          if (loaded) setMode({ kind: "chat" });
          else toast.error(t("history.loadFailed"));
        },
        (err: Error) => toast.error(err.message),
      );
    },
    [loadConversation, t],
  );

  const placeholder = pendingElicitation
    ? t("placeholderAnswer")
    : messages.length === 0
      ? t("placeholderEmpty")
      : t("placeholderRefine");

  const headerTitle =
    mode.kind === "chat" ? t("panelTitle") : mode.kind === "history" ? t("history.title") : (mode.title ?? "");

  // Back (and Continue) move focus to where the user lands: the composer in
  // the chat, the search box in History. Not on mount — only on a change.
  const prevModeRef = useRef<PanelMode["kind"] | null>(null);
  useEffect(() => {
    const previous = prevModeRef.current;
    prevModeRef.current = mode.kind;
    if (previous === null || previous === mode.kind) return;
    if (mode.kind === "chat") document.getElementById("ai-chat-input")?.focus();
    else if (mode.kind === "history") document.getElementById("ai-history-search")?.focus();
  }, [mode.kind]);

  // The live conversation's record was deleted from History: the hook drops
  // its id so the next autosave does not resurrect it (the transcript stays).
  const handleDeleted = useCallback(
    (id: string) => {
      if (id === conversationId) forgetConversation();
    },
    [conversationId, forgetConversation],
  );
  const handleCleared = useCallback(() => {
    if (conversationId) forgetConversation();
  }, [conversationId, forgetConversation]);

  return (
    <Flex ref={panelRef} direction="col" className="h-full min-h-0 w-full">
      <Card className="flex flex-1 min-h-0 w-full flex-col gap-0 overflow-hidden py-0">
        {/* Header: identity and navigation only. Ask / Auto is NOT here — it
            is in the composer's settings pill, with the provider and model,
            because everything that shapes the next send belongs above Send.
            (An older comment here claimed the opposite; the control moved and
            the comment did not.) In History / Review the left side becomes a
            Back button and the title names the view. */}
        <Box className="flex-shrink-0 border-b px-4 py-3">
          <Flex align="center" justify="between" gap="2">
            <Flex align="center" gap="2" className="min-w-0">
              {mode.kind === "chat" ? (
                <Sparkles className="h-4 w-4 shrink-0 text-brand-emphasis" aria-hidden="true" />
              ) : (
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-7 w-7 shrink-0"
                  onClick={() => setMode(mode.kind === "review" ? { kind: "history" } : { kind: "chat" })}
                  title={t("backAriaLabel")}
                  aria-label={t("backAriaLabel")}
                >
                  <ArrowLeft className="h-4 w-4" />
                </Button>
              )}
              <Text as="span" size="sm" weight="semibold" className="truncate">
                {headerTitle}
              </Text>
              {streaming && (
                <Text as="span" className="inline-flex" data-testid="ai-chat-streaming">
                  <Spinner size="sm" className="text-muted-foreground" label={null} />
                </Text>
              )}
            </Flex>
            <Flex align="center" gap="1" className="shrink-0">
              {mode.kind === "chat" ? (
                <>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    onClick={() => setMode({ kind: "history" })}
                    disabled={turnBusy}
                    title={t("historyAriaLabel")}
                    aria-label={t("historyAriaLabel")}
                  >
                    <History className="h-4 w-4" />
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    onClick={newConversation}
                    disabled={messages.length === 0}
                    title={t("newChatAriaLabel")}
                    aria-label={t("newChatAriaLabel")}
                  >
                    <SquarePen className="h-4 w-4" />
                  </Button>
                </>
              ) : null}
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                onClick={onClose}
                title={t("closePanelAriaLabel")}
                aria-label={t("closePanelAriaLabel")}
              >
                <X className="h-4 w-4" />
              </Button>
            </Flex>
          </Flex>
        </Box>

        {mode.kind === "history" ? (
          <AiHistoryList
            onOpen={(id) => setMode({ kind: "review", id, title: null })}
            onDeleted={handleDeleted}
            onCleared={handleCleared}
          />
        ) : mode.kind === "review" ? (
          <AiConversationReview
            id={mode.id}
            onContinue={handleContinue}
            onTitle={(title) => setMode((m) => (m.kind === "review" && m.id === mode.id ? { ...m, title } : m))}
          />
        ) : (
          <>
            {/* Observed steps of the current turn — outside the log so each is announced once. */}
            {currentTurn && (lastEntry?.pending || status === "awaiting_approval" || status === "awaiting_input") ? (
              <AiStepTimeline messages={messages} />
            ) : null}

            {/* Transcript */}
            <Conversation labels={{ conversation: t("messagesAriaLabel"), scrollToBottom: t("jumpToLatest") }}>
              <ConversationContent className="px-4 py-4">
                {messages.length === 0 && <EmptyState blocked={blocked} aiDisabled={aiDisabled} onPick={send} />}
                <TranscriptTurns
                  turns={turns}
                  pendingApproval={pendingApproval}
                  pendingElicitation={pendingElicitation}
                  busy={streaming}
                  onApprove={approve}
                  onAnswer={answer}
                />
                {error && status === "error" && (
                  <Alert variant="destructive" className="text-xs">
                    <AlertCircle className="h-3.5 w-3.5" />
                    <AlertDescription className="break-words">
                      {error}
                      <Box className="mt-1.5">
                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={retryLast}>
                          <RotateCcw className="mr-1 h-3 w-3" />
                          {t("retryButton")}
                        </Button>
                      </Box>
                    </AlertDescription>
                  </Alert>
                )}
              </ConversationContent>
              <ConversationScrollButton />
            </Conversation>

            {/* Composer. Everything that shapes the NEXT send lives here —
            the approval mode, the provider and model, the hint — because
            that is what the row above Send is for. The header is identity
            and navigation only.

            #2024 fixed a collision in this row by making every control
            shrinkable, which stopped the *painting* but left the cause: four
            controls competing for ~340px at the drawer's default width, the
            two pickers clipped to illegibility and two caption lines under
            them. #2047 removes the competition instead. The mode, the
            provider and the model now live behind one pill that states the
            two that matter ("Auto · sonnet-4"), so the row holds two items —
            pill and Send — and cannot collide at any width. The captions
            move inside the pill's popover, next to the control that
            produces them, which is where an explanation of Auto belongs
            anyway: at the moment of choosing, not below the composer
            afterwards. */}
            <Box className="flex-shrink-0 border-t bg-card px-3 py-3">
              {/* A turn that hit a per-turn cap stopped mid-work with
                  everything it had done already saved in the transcript.
                  Offering to carry on is the difference between a checkpoint
                  and a dead end — without it the only way forward is to
                  guess that typing "continue" works. */}
              {mode.kind === "chat" && pausedAtLimit ? (
                <Flex
                  align="center"
                  justify="between"
                  gap="2"
                  className="mb-2 rounded-md border border-border/60 bg-muted/40 px-2.5 py-2"
                  data-testid="ai-keep-going"
                >
                  <Text size="xs" tone="muted" className="min-w-0">
                    {t("keepGoing.prompt")}
                  </Text>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="h-7 shrink-0"
                    onClick={continueTurn}
                    disabled={streaming}
                    data-testid="ai-keep-going-button"
                  >
                    {t("keepGoing.action")}
                  </Button>
                </Flex>
              ) : null}
              <Label htmlFor="ai-chat-input" className="sr-only">
                {t("messageLabel")}
              </Label>
              <PromptInput
                status={composerStatus}
                labels={{ send: t("sendButton"), stop: t("stopButton") }}
                onSubmit={handleSubmit}
              >
                <PromptInputTextarea
                  id="ai-chat-input"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={placeholder}
                  disabled={blocked}
                  minRows={2}
                />
                <PromptInputToolbar>
                  {/* Two items in this row, and only one of them flexible:
                      the pill (min-w-0, truncating) and Send (shrink-0).
                      Keep it that way — every past collision here came from
                      a third control arriving to compete for the same
                      ~340px. New chat-scoped settings belong inside the
                      pill's popover, not beside it. */}
                  <PromptInputTools className="min-w-0 flex-1 flex-nowrap gap-1.5 overflow-hidden">
                    <ComposerSettingsPill
                      approvalMode={effectiveMode}
                      onApprovalModeChange={handleModeChange}
                      approvalModeDisabled={!settings}
                      autoNote={autoNote}
                      autoForThisChatOnly={autoForThisChatOnly}
                      providers={providers}
                      providerId={effectiveProviderId}
                      onProviderChange={(v) => {
                        setProviderId(v);
                        setModel("");
                      }}
                      models={availableModels}
                      model={effectiveModel}
                      onModelChange={setModel}
                    />
                  </PromptInputTools>
                  <Flex align="center" gap="2" className="min-w-0 shrink">
                    {/* Sighted pointer users get the bindings from this hint;
                    screen readers get them from `aria-keyshortcuts` on the
                    button, so the hint stays out of the accessibility tree.
                    Touch keyboards have no Shift+Enter, so coarse pointers
                    do not see it at all. Keycap glyphs are never translated;
                    the verbs are. It renders only when the row is wide
                    enough to hold it beside the pickers; below that it is
                    the Send button's tooltip — same information, no
                    overlap. */}
                    {showSendHint ? (
                      <Text
                        as="span"
                        size="xs"
                        tone="muted"
                        aria-hidden="true"
                        data-testid="ai-chat-send-hint"
                        className="inline-flex min-w-0 shrink items-center gap-1.5 truncate pointer-coarse:hidden"
                      >
                        <Kbd keys={["Enter"]} />
                        {t("enterToSend")}
                        <Kbd keys={["Shift", "Enter"]} />
                        {t("shiftEnterNewline")}
                      </Text>
                    ) : null}
                    {/* The hint's information, for the widths where the hint
                        itself does not fit. A `title` rather than the design
                        system's Tooltip on purpose: TooltipTrigger's `asChild`
                        overrides the child's own `onClick` (it clones the
                        element with its own handlers), which silently broke
                        Stop — the composer's most important button while a
                        turn is running. Flagged for the package in the PR;
                        `aria-keyshortcuts` is what assistive tech reads
                        either way. */}
                    <PromptInputSubmit
                      className="shrink-0"
                      aria-keyshortcuts="Enter"
                      title={showSendHint ? undefined : t("sendShortcut")}
                      onStop={stop}
                      disabled={blocked || (!streaming && !draft.trim())}
                    />
                  </Flex>
                </PromptInputToolbar>
              </PromptInput>
            </Box>
          </>
        )}
      </Card>
    </Flex>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function GradientSparkles({ className }: { className?: string }) {
  return (
    <Text as="span" className={`relative inline-block shrink-0 ${className ?? ""}`} aria-hidden="true">
      <Text as="span" className="ai-sparkle-icon absolute inset-0 h-full w-full" />
      <svg
        viewBox="0 0 24 24"
        fill="none"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="absolute inset-0 h-full w-full"
      >
        <defs>
          <linearGradient id="ai-sg" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
            <stop offset="0%" style={{ stopColor: "var(--ai-sg-c1, #c97a72)" }} />
            <stop offset="40%" style={{ stopColor: "var(--ai-sg-c2, #c99662)" }} />
            <stop offset="70%" style={{ stopColor: "var(--ai-sg-c3, #9b7bb0)" }} />
            <stop offset="100%" style={{ stopColor: "var(--ai-sg-c1, #c97a72)" }} />
          </linearGradient>
        </defs>
        <g className="sparkle-cross">
          <path stroke="url(#ai-sg)" d="M20 2v4" />
          <path stroke="url(#ai-sg)" d="M22 4h-4" />
        </g>
        <circle className="sparkle-circ" cx={4} cy={20} r={2} stroke="url(#ai-sg)" />
      </svg>
    </Text>
  );
}

function EmptyState({
  blocked,
  aiDisabled,
  onPick,
}: {
  blocked: boolean;
  aiDisabled: boolean;
  onPick: (text: string) => void;
}) {
  const t = useTranslations("aiChatPanel");
  if (blocked) {
    return (
      <Alert variant="destructive" className="text-xs">
        <AlertCircle className="h-3.5 w-3.5" />
        <AlertDescription>{aiDisabled ? t("blockedAiDisabled") : t("blockedNoProviders")}</AlertDescription>
      </Alert>
    );
  }
  const starters = [t("suggestions.weather"), t("suggestions.date"), t("suggestions.variables")];
  return (
    <Flex direction="col" align="center" gap="5" className="px-2 py-6 text-center">
      <GradientSparkles className="h-8 w-8" />
      <Box>
        <Text weight="medium">{t("emptyStateTitle")}</Text>
        <Text size="xs" tone="muted" className="mt-1">
          {t("emptyStateDescription")}
        </Text>
      </Box>
      {/* Wrapped, not a sideways scroller: three starters in a 384px drawer
          became a scrollbar with two chips half off the edge (#2024). */}
      <Suggestions className="flex-wrap justify-center overflow-x-visible whitespace-normal">
        {starters.map((s) => (
          <Suggestion key={s} suggestion={s} onClick={onPick} />
        ))}
      </Suggestions>
    </Flex>
  );
}

/** The model name without its vendor prefix — `anthropic/sonnet-4` → `sonnet-4`. */
function shortModelName(model: string): string {
  return model.split("/").slice(-1)[0] || model;
}

/**
 * Everything that shapes the next send, behind one pill in the composer
 * toolbar: the approval mode, the provider and the model.
 *
 * The pill's face is the two facts worth reading at a glance — the mode and
 * the model — and the popover is where they change. That trade is the point
 * (#2047): the row it sits in is ~340px wide at the drawer's default, which
 * is not enough for a segmented control plus two selects, and the previous
 * attempt to make them all shrink produced a row of clipped, unreadable
 * controls with the mode's `whitespace-nowrap` labels painting over the
 * model pill beside them.
 *
 * The trigger is a real `<button>` (no `asChild`), so nothing clones it and
 * drops the handler that opens it — the failure mode already recorded on
 * `PromptInputSubmit` below.
 */
function ComposerSettingsPill({
  approvalMode,
  onApprovalModeChange,
  approvalModeDisabled,
  autoNote,
  autoForThisChatOnly,
  providers,
  providerId,
  onProviderChange,
  models,
  model,
  onModelChange,
}: {
  approvalMode: AiApprovalMode;
  /** Takes the raw value: `SegmentedControl` emits `string`, and the panel's
      handler is what narrows it to a mode. */
  onApprovalModeChange: (value: string) => void;
  approvalModeDisabled: boolean;
  autoNote: boolean;
  autoForThisChatOnly: boolean;
  providers: AISettings["providers"];
  providerId: string;
  onProviderChange: (id: string) => void;
  models: string[];
  model: string;
  onModelChange: (m: string) => void;
}) {
  const t = useTranslations("aiChatPanel");
  const onlyOneProvider = providers.length <= 1;
  const shortModel = model ? shortModelName(model) : t("defaultModel");
  const modeLabel = t(`approvalMode.${approvalMode}`);
  return (
    <Popover>
      {/* `min-w-0` + a truncating label: the pill yields width to Send
          rather than pushing it off the row. */}
      <PopoverTrigger
        className="inline-flex h-7 min-w-0 shrink items-center gap-1.5 rounded-full border border-border/60 bg-muted/40 px-2.5 text-[11px] text-foreground transition-colors hover:bg-muted/70 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
        aria-label={t("composerSettings.triggerAriaLabel", { mode: modeLabel, model: shortModel })}
        data-testid="ai-composer-settings"
      >
        <SlidersHorizontal className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
        <Text as="span" className="truncate text-[11px]" aria-hidden="true">
          {modeLabel} ·{" "}
          <Text as="span" className="font-mono text-[11px]">
            {shortModel}
          </Text>
        </Text>
      </PopoverTrigger>
      <PopoverContent align="start" side="top" className="w-72 p-3" label={t("composerSettings.popoverLabel")}>
        <Flex direction="col" gap="3">
          <Flex direction="col" gap="1.5">
            {/* Not a <Label>: a radiogroup takes its name from
                `aria-label` (below), and a <label for> pointing at one
                names nothing. This is the visible heading only. */}
            <Text as="span" size="xs" weight="medium" aria-hidden="true">
              {t("approvalMode.label")}
            </Text>
            <SegmentedControl
              aria-label={t("approvalMode.label")}
              size="sm"
              layout="grid"
              columns="2"
              value={approvalMode}
              onValueChange={onApprovalModeChange}
              disabled={approvalModeDisabled}
              data-testid="ai-approval-mode"
            >
              <SegmentedControlItem value="ask">{t("approvalMode.ask")}</SegmentedControlItem>
              <SegmentedControlItem value="auto">{t("approvalMode.auto")}</SegmentedControlItem>
            </SegmentedControl>
            {/* What Auto means, shown where Auto is chosen. */}
            {autoNote ? (
              <Text size="xs" tone="muted" data-testid="ai-approval-mode-note">
                {t("approvalMode.autoNote")}
              </Text>
            ) : null}
            {autoForThisChatOnly ? (
              <Text size="xs" tone="muted" data-testid="ai-approval-mode-this-chat">
                {t("approvalMode.thisChat")}
              </Text>
            ) : null}
          </Flex>

          {!onlyOneProvider && (
            <Flex direction="col" gap="1.5">
              <Label htmlFor="ai-provider-select" className="text-xs">
                {t("providerSelectAriaLabel")}
              </Label>
              <Select value={providerId} onValueChange={onProviderChange}>
                <SelectTrigger id="ai-provider-select" className="h-8 text-xs">
                  <SelectValue placeholder={t("defaultModel")} />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((p) => (
                    <SelectItem key={p.id} value={p.id} className="text-xs">
                      {p.name || p.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Flex>
          )}

          <Flex direction="col" gap="1.5">
            <Label htmlFor="ai-model-select" className="text-xs">
              {t("modelSelectAriaLabel")}
            </Label>
            <Select value={model} onValueChange={onModelChange} disabled={models.length === 0}>
              <SelectTrigger id="ai-model-select" className="h-8 font-mono text-xs" title={model}>
                <SelectValue>
                  <Text as="span" className="truncate font-mono text-xs">
                    {shortModel}
                  </Text>
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {models.map((m) => (
                  <SelectItem key={m} value={m} className="font-mono text-xs">
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Flex>
        </Flex>
      </PopoverContent>
    </Popover>
  );
}
