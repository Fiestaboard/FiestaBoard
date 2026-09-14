"use client";

import {
  Alert,
  AlertDescription,
  Box,
  Button,
  Card,
  Code,
  Conversation,
  ConversationContent,
  ConversationScrollButton,
  Flex,
  Label,
  Message,
  MessageAvatar,
  MessageContent,
  PromptInput,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputToolbar,
  PromptInputTools,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Suggestion,
  Suggestions,
  Text,
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
  type ToolState,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, RotateCcw, Sparkles, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AiApprovalCard } from "@/components/ai-approval-card";
import { AiQuestionCard } from "@/components/ai-question-card";
import { AiStepTimeline } from "@/components/ai-step-timeline";
import { detailForTool, labelForTool } from "@/components/ai-tool-labels";
import { ChatMarkdown } from "@/components/chat-markdown";
import { InlineBoardPreview } from "@/components/inline-board-preview";
import { useTranslations } from "@/i18n/translations";
import type {
  ApprovalDecision,
  ChatMessage,
  ChatTurnContext,
  Elicitation,
  ElicitationAnswer,
  SSEStatusData,
  ToolCall,
  ToolCallDisplay,
  ToolPhase,
  ToolResult,
} from "@/lib/ai-chat-types";
import { type AISettings, api } from "@/lib/api";
import { useAiChat } from "@/lib/use-ai-chat";

/** What the drawer can drive from outside the panel (spotlight controls, later). */
export interface AiChatController {
  approve: (toolCallId: string, decision: ApprovalDecision) => void;
  answer: (toolCallId: string, answer: ElicitationAnswer) => void;
  stop: () => void;
}

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
  /** The user stopped the turn with these calls still running server-side. */
  onStopped?: (unresolved: ToolCall[]) => void;
  /** Close button hides the panel without losing the existing layout. */
  onClose: () => void;
  /**
   * Slot ref: the panel writes its controller here so a sibling (the
   * drawer's spotlight strip) can approve, answer or stop without
   * prop-drilling through the conversation.
   */
  controllerRef?: React.MutableRefObject<AiChatController | null>;
}

export function AiChatPanel({
  getTurnContext,
  onToolCall,
  onToolResult,
  onAwaitingApproval,
  onElicitation,
  onStatus,
  onStopped,
  onClose,
  controllerRef,
}: AiChatPanelProps) {
  const t = useTranslations("aiChatPanel");
  const [providerId, setProviderId] = useState<string>("");
  const [model, setModel] = useState<string>("");
  const [draft, setDraft] = useState("");

  const { data: settings } = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: () => api.getAiSettings(),
  });

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
    reset,
  } = useAiChat({
    getTurnContext,
    onToolCall,
    onToolResult,
    onAwaitingApproval,
    onElicitation,
    onStatus,
    onStopped,
    providerId: effectiveProviderId || undefined,
    model: effectiveModel || undefined,
  });

  // Slot-ref pattern: keep the parent's ref pointed at the latest controller.
  useEffect(() => {
    if (controllerRef) controllerRef.current = { approve, answer, stop };
  }, [controllerRef, approve, answer, stop]);

  const streaming = status === "streaming";
  const composerStatus = streaming ? "streaming" : status === "error" ? "error" : "ready";

  const lastAssistant = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return messages[i];
    }
    return null;
  }, [messages]);

  const handleSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!draft.trim() || blocked || streaming) return;
      send(draft);
      setDraft("");
    },
    [draft, blocked, streaming, send],
  );

  const placeholder = pendingElicitation
    ? t("placeholderAnswer")
    : messages.length === 0
      ? t("placeholderEmpty")
      : t("placeholderRefine");

  return (
    <Flex direction="col" className="h-full min-h-0 w-full">
      <Card className="flex flex-1 min-h-0 w-full flex-col gap-0 overflow-hidden py-0">
        {/* Header */}
        <Flex align="center" justify="between" gap="2" className="flex-shrink-0 border-b px-4 py-3">
          <Flex align="center" gap="2" className="min-w-0">
            <Sparkles className="h-4 w-4 shrink-0 text-brand-emphasis" aria-hidden="true" />
            <Text as="span" size="sm" weight="semibold" className="truncate">
              {t("panelTitle")}
            </Text>
            {streaming && <Spinner size="sm" className="text-muted-foreground" label={null} />}
          </Flex>
          <Flex align="center" gap="1">
            {messages.length > 0 && (
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                onClick={reset}
                title={t("clearConversationAriaLabel")}
                aria-label={t("clearConversationAriaLabel")}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
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

        {/* Observed steps of the current turn — outside the log so each is announced once. */}
        {lastAssistant && (lastAssistant.pending || status === "awaiting_approval" || status === "awaiting_input") ? (
          <AiStepTimeline message={lastAssistant} />
        ) : null}

        {/* Transcript */}
        <Conversation labels={{ conversation: t("messagesAriaLabel"), scrollToBottom: t("jumpToLatest") }}>
          <ConversationContent className="px-4 py-4">
            {messages.length === 0 && <EmptyState blocked={blocked} aiDisabled={aiDisabled} onPick={send} />}
            {messages.map((m, i) => (
              <ChatTurn
                key={i}
                message={m}
                isLast={i === messages.length - 1}
                pendingApproval={pendingApproval}
                pendingElicitation={pendingElicitation}
                busy={streaming}
                onApprove={approve}
                onAnswer={answer}
              />
            ))}
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
                {/* Keyboard shortcut glyphs are never translated. */}
                <Code className="bg-transparent px-0 py-0 text-[10px] text-muted-foreground">Enter</Code>
              </PromptInputTools>
              <PromptInputSubmit onStop={stop} disabled={blocked || (!streaming && !draft.trim())} />
            </PromptInputToolbar>
          </PromptInput>
        </Box>
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

function ChatTurn({
  message,
  isLast,
  pendingApproval,
  pendingElicitation,
  busy,
  onApprove,
  onAnswer,
}: {
  message: ChatMessage;
  isLast: boolean;
  pendingApproval: ToolCall | null;
  pendingElicitation: Elicitation | null;
  busy: boolean;
  onApprove: (id: string, decision: ApprovalDecision) => void;
  onAnswer: (id: string, answer: ElicitationAnswer) => void;
}) {
  if (message.role === "user") {
    return (
      <Message from="user">
        <MessageContent className="whitespace-pre-wrap break-words">{message.content}</MessageContent>
      </Message>
    );
  }

  return (
    <Message from="assistant">
      <MessageAvatar>
        <Sparkles />
      </MessageAvatar>
      <MessageContent>
        <Stack gap="2">
          {message.content && (
            <Box className="break-words text-sm">
              <ChatMarkdown>{message.content}</ChatMarkdown>
            </Box>
          )}
          {message.toolCalls
            ?.filter((call) => call.name !== "ask_user")
            .map((call) => (
              <Stack key={call.id} gap="1.5">
                <ToolCallCard call={call} />
                {isLast && pendingApproval?.id === call.id && call.phase === "awaiting_approval" ? (
                  <AiApprovalCard
                    call={call}
                    busy={busy}
                    onApprove={() => onApprove(call.id, "approve")}
                    onDeny={() => onApprove(call.id, "deny")}
                  />
                ) : null}
              </Stack>
            ))}
          {message.elicitation ? (
            <AiQuestionCard
              elicitation={message.elicitation}
              busy={busy || (isLast && pendingElicitation === null && !message.elicitation.answer)}
              onAnswer={(a) => onAnswer(message.elicitation!.id, a)}
            />
          ) : null}
          {message.warnings && message.warnings.length > 0 && (
            <Stack gap="1">
              {message.warnings.map((w, i) => (
                <Alert key={i} className="py-1.5 text-xs">
                  <AlertCircle className="h-3 w-3" />
                  <AlertDescription>{w}</AlertDescription>
                </Alert>
              ))}
            </Stack>
          )}
        </Stack>
      </MessageContent>
    </Message>
  );
}

const TOOL_STATE_FOR_PHASE: Record<ToolPhase, ToolState> = {
  running: "input-available",
  awaiting_approval: "approval-requested",
  ok: "output-available",
  blocked: "output-error",
  error: "output-error",
  denied: "denied",
  stopped: "stopped",
};

function ToolCallCard({ call }: { call: ToolCallDisplay }) {
  const t = useTranslations("aiChatPanel");
  const deviceType = call.deviceType ?? "flagship";
  const state = TOOL_STATE_FOR_PHASE[call.phase];
  const result = call.result;
  const errorText =
    result && (result.status === "error" || result.status === "blocked") ? (result.error ?? result.summary) : undefined;
  const output =
    result && result.status === "ok" ? (
      <Stack gap="2">
        {call.appliedSnapshot ? <InlineBoardPreview snapshot={call.appliedSnapshot} deviceType={deviceType} /> : null}
        <Text size="xs">{result.summary}</Text>
      </Stack>
    ) : call.appliedSnapshot ? (
      <InlineBoardPreview snapshot={call.appliedSnapshot} deviceType={deviceType} />
    ) : undefined;

  return (
    <Tool
      state={state}
      data-testid={`ai-tool-${call.name}`}
      labels={{
        input: t("toolInput"),
        output: t("toolOutput"),
        states: {
          "input-streaming": t("toolStates.inputStreaming"),
          "input-available": t("toolStates.inputAvailable"),
          "output-available": t("toolStates.outputAvailable"),
          "output-error": t("toolStates.outputError"),
          "approval-requested": t("toolStates.approvalRequested"),
          denied: t("toolStates.denied"),
          stopped: t("toolStates.stopped"),
        },
      }}
    >
      <ToolHeader title={labelForTool(call, t)} detail={detailForTool(call)} />
      <ToolContent>
        <ToolInput input={call.args} />
        <ToolOutput output={output} errorText={errorText} />
      </ToolContent>
    </Tool>
  );
}
