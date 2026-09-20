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
import { AlertCircle, ArrowLeft, History, RotateCcw, Sparkles, SquarePen, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { AiConversationReview, AiHistoryList, CONVERSATIONS_QUERY_KEY } from "@/components/ai-chat-history";
import { groupTurns, TranscriptTurns } from "@/components/ai-chat-transcript";
import { AiStepTimeline } from "@/components/ai-step-timeline";
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
    <Flex direction="col" className="h-full min-h-0 w-full">
      <Card className="flex flex-1 min-h-0 w-full flex-col gap-0 overflow-hidden py-0">
        {/* Header. The Ask / Auto approval mode lives here, not in the
            composer toolbar: it is a property of the whole chat, not of the
            next message. In History / Review the left side becomes a Back
            button and the title names the view. */}
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
            <Flex align="center" gap="1">
              {mode.kind === "chat" ? (
                <>
                  <SegmentedControl
                    aria-label={t("approvalMode.label")}
                    size="sm"
                    value={effectiveMode}
                    onValueChange={handleModeChange}
                    disabled={!settings}
                    className="mr-1"
                    data-testid="ai-approval-mode"
                  >
                    <SegmentedControlItem value="ask">{t("approvalMode.ask")}</SegmentedControlItem>
                    <SegmentedControlItem value="auto">{t("approvalMode.auto")}</SegmentedControlItem>
                  </SegmentedControl>
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
          {mode.kind === "chat" && autoNote ? (
            <Text size="xs" tone="muted" className="mt-2" data-testid="ai-approval-mode-note">
              {t("approvalMode.autoNote")}
            </Text>
          ) : null}
          {mode.kind === "chat" && autoForThisChatOnly ? (
            <Text size="xs" tone="muted" className="mt-2" data-testid="ai-approval-mode-this-chat">
              {t("approvalMode.thisChat")}
            </Text>
          ) : null}
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

            {/* Composer. The provider + model pills sit below the input: the
            model is a property of the next turn, not chrome at the top. */}
            <Box className="flex-shrink-0 border-t bg-card px-3 py-3">
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
                  <PromptInputTools className="min-w-0 flex-wrap">
                    <ModelPill
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
                  <Flex align="center" gap="2" className="shrink-0">
                    {/* Sighted pointer users get the bindings from this hint;
                    screen readers get them from `aria-keyshortcuts` on the
                    button, so the hint stays out of the accessibility tree.
                    Touch keyboards have no Shift+Enter, so coarse pointers
                    do not see it at all. Keycap glyphs are never translated;
                    the verbs are. */}
                    <Text
                      as="span"
                      size="xs"
                      tone="muted"
                      aria-hidden="true"
                      data-testid="ai-chat-send-hint"
                      className="inline-flex items-center gap-1.5 whitespace-nowrap pointer-coarse:hidden"
                    >
                      <Kbd keys={["Enter"]} />
                      {t("enterToSend")}
                      <Kbd keys={["Shift", "Enter"]} />
                      {t("shiftEnterNewline")}
                    </Text>
                    <PromptInputSubmit
                      aria-keyshortcuts="Enter"
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
      <Suggestions className="justify-center">
        {starters.map((s) => (
          <Suggestion key={s} suggestion={s} onClick={onPick} />
        ))}
      </Suggestions>
    </Flex>
  );
}

/**
 * Compact model picker rendered in the composer toolbar — same pattern
 * as ChatGPT/Claude/etc. Shows a single pill with `provider · model`.
 */
function ModelPill({
  providers,
  providerId,
  onProviderChange,
  models,
  model,
  onModelChange,
}: {
  providers: AISettings["providers"];
  providerId: string;
  onProviderChange: (id: string) => void;
  models: string[];
  model: string;
  onModelChange: (m: string) => void;
}) {
  const t = useTranslations("aiChatPanel");
  const onlyOneProvider = providers.length <= 1;
  const shortModel = model ? model.split("/").slice(-1)[0] || model : t("defaultModel");
  return (
    <Flex align="center" gap="1">
      {!onlyOneProvider && (
        <Select value={providerId} onValueChange={onProviderChange}>
          <SelectTrigger
            className="h-6 gap-1 rounded-full border-border/60 bg-muted/40 px-2 text-[11px] shadow-none hover:bg-muted/70"
            aria-label={t("providerSelectAriaLabel")}
          >
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
      )}
      <Select value={model} onValueChange={onModelChange} disabled={models.length === 0}>
        <SelectTrigger
          className="h-6 max-w-[180px] gap-1 truncate rounded-full border-border/60 bg-muted/40 px-2 font-mono text-[11px] shadow-none hover:bg-muted/70"
          aria-label={t("modelSelectAriaLabel")}
          title={model}
        >
          <SelectValue>
            <Text as="span" className="truncate font-mono text-[11px]">
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
  );
}
