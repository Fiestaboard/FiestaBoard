"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Eye,
  EyeOff,
  Loader2,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  Trash2,
  Undo2,
  X,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ChatMarkdown } from "@/components/chat-markdown";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { InlineBoardPreview } from "@/components/inline-board-preview";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, type AISettings } from "@/lib/api";
import type {
  ChainingMode,
  ChatMessage,
  ChatTurnContext,
  LineOp,
  ToolCall,
  ToolCallDisplay,
} from "@/lib/ai-chat-types";
import { useAiChat } from "@/lib/use-ai-chat";
import { ChainingModePicker } from "@/components/chaining-mode-picker";

export interface AiChatPanelProps {
  /** Per-turn editor context (device type + current page snapshot). */
  getTurnContext: () => ChatTurnContext;
  /** Editor mutation hook — invoked when a validated tool call arrives. */
  onToolCall: (call: ToolCall) => void;
  /** Show an Undo button next to a successfully applied mutation. */
  canUndo?: boolean;
  onUndo?: () => void;
  /** Close button hides the panel without losing the existing layout. */
  onClose: () => void;
  /**
   * Optional renderer for supplemental content below a tool call card.
   * Used by the global AI drawer to render confirmation cards for
   * install_plugin, update_setting, etc.
   */
  renderToolCallSupplement?: (call: ToolCall) => React.ReactNode;
  /**
   * Slot ref: parent writes into this ref so sibling components can
   * call `resume(toolResultText)` after tool execution completes.
   * The slot is populated from the `resume` function returned by
   * `useAiChat`, so it always points at the latest closure.
   */
  resumeFnRef?: React.MutableRefObject<((text: string) => void) | null>;
  /** Current AI chaining mode (controlled by parent). */
  chainingMode?: ChainingMode;
  /** Called when the user changes the chaining mode via the in-panel picker. */
  onChainingModeChange?: (mode: ChainingMode) => void;
}

export function AiChatPanel({
  getTurnContext,
  onToolCall,
  canUndo = false,
  onUndo = () => {},
  onClose,
  renderToolCallSupplement,
  resumeFnRef,
  chainingMode = "manual",
  onChainingModeChange,
}: AiChatPanelProps) {
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
    model && availableModels.includes(model)
      ? model
      : selectedProvider?.default_model ?? availableModels[0] ?? "";

  const aiDisabled = settings ? !settings.enabled : false;
  const noProviders = providers.length === 0;
  const noModels = !!selectedProvider && !effectiveModel;
  const blocked = aiDisabled || noProviders || noModels;

  const { messages, status, error, send, resume, cancel, retryLast, reset } =
    useAiChat({
      getTurnContext,
      onToolCall,
      providerId: effectiveProviderId || undefined,
      model: effectiveModel || undefined,
    });

  // Slot-ref pattern: keep the parent's ref pointed at the latest resume fn.
  useEffect(() => {
    if (resumeFnRef) resumeFnRef.current = resume;
  }, [resumeFnRef, resume]);

  // Boards beyond the 3 most recent are collapsed by default.
  // Users can manually expand them; that choice is tracked here.
  const [manuallyExpandedBoardIds, setManuallyExpandedBoardIds] = useState<Set<string>>(
    new Set(),
  );

  const allBoardIds = useMemo(() => {
    const ids: string[] = [];
    for (const msg of messages) {
      for (const call of msg.toolCalls ?? []) {
        if (call.appliedSnapshot) ids.push(call.id);
      }
    }
    return ids;
  }, [messages]);

  const isBoardVisible = (callId: string) => {
    const idx = allBoardIds.indexOf(callId);
    return idx >= allBoardIds.length - 3 || manuallyExpandedBoardIds.has(callId);
  };

  const toggleBoard = (callId: string) => {
    setManuallyExpandedBoardIds((prev) => {
      const next = new Set(prev);
      if (next.has(callId)) next.delete(callId);
      else next.add(callId);
      return next;
    });
  };

  const handleSubmit = () => {
    if (!draft.trim() || blocked || status === "streaming") return;
    send(draft);
    setDraft("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Outer wrapper hugs the chat-side edge: full vertical breathing
  // room, **no left padding** so the Card's left border doubles as
  // the resize handle, and a generous right inset to balance the
  // visual weight of the global navigation sidebar on the far-left
  // edge of the page.
  return (
    <div className="flex h-full min-h-0 w-full flex-col pl-0 pr-3 sm:pr-4 md:pr-6 py-4 sm:py-6 md:py-8 lg:py-3">
      <Card className="flex flex-1 min-h-0 w-full flex-col gap-0 overflow-hidden py-0">
        {/* Header */}
        <div className="flex flex-shrink-0 items-center justify-between gap-2 border-b px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <Sparkles className="h-4 w-4 shrink-0 text-brand-emphasis" />
            <span className="truncate text-sm font-semibold">FiestaBot (Beta)</span>
            {status === "streaming" && (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
            )}
          </div>
          <div className="flex items-center gap-1">
            {onChainingModeChange && (
              <ChainingModePicker
                mode={chainingMode}
                onChange={onChainingModeChange}
              />
            )}
            {messages.length > 0 && (
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                onClick={reset}
                title="Clear conversation"
                aria-label="Clear conversation"
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
              title="Close FiestaBot (Beta)"
              aria-label="Close FiestaBot (Beta)"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Messages — scrollable middle section */}
        <ScrollArea className="min-h-0 flex-1">
          <div className="min-w-0 max-w-full overflow-x-hidden space-y-3 px-4 py-4">
            {messages.length === 0 && (
              <EmptyState blocked={blocked} aiDisabled={aiDisabled} />
            )}
            {messages.map((m, i) => (
              <MessageBubble
                key={i}
                message={m}
                isLastAssistant={
                  m.role === "assistant" && i === messages.length - 1
                }
                canUndo={canUndo}
                onUndo={onUndo}
                isBoardVisible={isBoardVisible}
                onToggleBoard={toggleBoard}
                renderToolCallSupplement={renderToolCallSupplement}
              />
            ))}
            {error && status === "error" && (
              <Alert variant="destructive" className="text-xs">
                <AlertCircle className="h-3.5 w-3.5" />
                <AlertDescription className="break-words">
                  {error}
                  <div className="mt-1.5">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs"
                      onClick={retryLast}
                    >
                      <RotateCcw className="mr-1 h-3 w-3" />
                      Retry
                    </Button>
                  </div>
                </AlertDescription>
              </Alert>
            )}
          </div>
        </ScrollArea>

        {/* Sticky composer at the bottom of the Card.
         *  Provider + model pickers sit BELOW the input as compact
         *  pills — same pattern as ChatGPT / Claude / other LLM UIs:
         *  the model is a property of the next turn, not chrome at the
         *  top of the panel. This also frees vertical space and works
         *  well in narrow chat-pane widths. */}
        <div className="flex flex-shrink-0 flex-col gap-2 border-t bg-card px-4 py-4">
          <Label htmlFor="ai-chat-input" className="sr-only">
            Message
          </Label>
          <Textarea
            id="ai-chat-input"
            rows={3}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              messages.length === 0
                ? "Describe the page you want, or ask for changes…"
                : "Refine, ask, or request another change…"
            }
            disabled={blocked}
            className="resize-none px-3 py-3 text-sm"
          />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
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
              <span className="text-[10px] text-muted-foreground">
                ⌘/Ctrl+Enter
              </span>
            </div>
            {status === "streaming" ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 gap-1 text-xs"
                onClick={cancel}
              >
                <Square className="h-3 w-3" />
                Stop
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                variant="brand"
                className="h-7 gap-1 text-xs"
                onClick={handleSubmit}
                disabled={!draft.trim() || blocked}
              >
                <Send className="h-3 w-3" />
                Send
              </Button>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function GradientSparkles({ className }: { className?: string }) {
  return (
    <span
      className={`relative inline-block shrink-0 ${className ?? ""}`}
      aria-hidden="true"
    >
      {/* Big central star — gradient sweep via CSS mask */}
      <span className="ai-sparkle-icon absolute inset-0 h-full w-full" />
      {/* Small elements — pulse independently from their own centers */}
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
    </span>
  );
}

function EmptyState({
  blocked,
  aiDisabled,
}: {
  blocked: boolean;
  aiDisabled: boolean;
}) {
  if (blocked) {
    return (
      <Alert variant="destructive" className="text-xs">
        <AlertCircle className="h-3.5 w-3.5" />
        <AlertDescription>
          {aiDisabled
            ? "AI is disabled. Enable it in Settings → AI Providers."
            : "Configure an AI provider with at least one model in Settings → AI Providers."}
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <div className="flex flex-col items-center gap-5 px-2 py-6 text-center">
      <GradientSparkles className="h-8 w-8" />
      <div>
        <p className="text-sm font-medium">How can I help?</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Describe what you&apos;d like to build or change.
        </p>
      </div>
      <div className="w-full space-y-2 text-left text-xs">
        {[
          "Build a weather + transit page for my morning commute",
          "Replace line 2 with today’s date",
          "What plugin variables can I use on this page?",
        ].map((s) => (
          <div
            key={s}
            className="flex items-start gap-2 text-muted-foreground"
          >
            <ChevronRight className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground/50" />
            <span>&ldquo;{s}&rdquo;</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Compact model picker rendered next to the Send button — same pattern
 * as ChatGPT/Claude/etc. Shows a single pill with `provider · model`,
 * collapses to icons when there's no horizontal room. We surface both
 * provider and model as nested selects so multi-provider users still
 * have the full picker without dedicating header real estate to it.
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
  const onlyOneProvider = providers.length <= 1;
  const shortModel = model
    ? model.split("/").slice(-1)[0] || model
    : "Default";
  return (
    <div className="flex items-center gap-1">
      {!onlyOneProvider && (
        <Select
          value={providerId}
          onValueChange={onProviderChange}
        >
          <SelectTrigger
            className="h-6 gap-1 rounded-full border-border/60 bg-muted/40 px-2 text-[11px] shadow-none hover:bg-muted/70"
            aria-label="Provider"
          >
            <SelectValue placeholder="Default" />
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
      <Select
        value={model}
        onValueChange={onModelChange}
        disabled={models.length === 0}
      >
        <SelectTrigger
          className="h-6 max-w-[180px] gap-1 truncate rounded-full border-border/60 bg-muted/40 px-2 font-mono text-[11px] shadow-none hover:bg-muted/70"
          aria-label="Model"
          title={model}
        >
          <SelectValue>
            <span className="truncate">{shortModel}</span>
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
    </div>
  );
}

function MessageBubble({
  message,
  isLastAssistant,
  canUndo,
  onUndo,
  isBoardVisible,
  onToggleBoard,
  renderToolCallSupplement,
}: {
  message: ChatMessage;
  isLastAssistant: boolean;
  canUndo: boolean;
  onUndo: () => void;
  isBoardVisible: (callId: string) => boolean;
  onToggleBoard: (callId: string) => void;
  renderToolCallSupplement?: (call: ToolCall) => React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // Scroll the latest message into view as it streams.
  useEffect(() => {
    if (isLastAssistant) {
      ref.current?.scrollIntoView({ block: "end", behavior: "smooth" });
    }
  }, [isLastAssistant, message.content, message.toolCalls?.length]);

  if (message.role === "user") {
    // Tool-result injection messages get a compact system pill, not a user bubble.
    if (message.isToolResult) {
      const displayText = message.content
        .replace(/^\[Tool result:\s*/, "")
        .replace(/\]$/, "");
      return (
        <div ref={ref} className="flex justify-center py-0.5">
          <div className="flex items-center gap-1.5 overflow-hidden rounded-full border border-border/40 bg-muted/30 px-2.5 py-1 text-[10px] text-muted-foreground max-w-[85%]">
            <CheckCircle2 className="h-3 w-3 shrink-0 text-green-500" />
            <span className="min-w-0 truncate font-mono">{displayText}</span>
          </div>
        </div>
      );
    }
    return (
      <div ref={ref} className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-brand-emphasis/15 px-3 py-2 text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div ref={ref} className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5">
        <Sparkles className="h-3 w-3 text-brand-emphasis" />
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          AI
        </span>
        {message.pending && (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
        )}
      </div>
      {message.content && (
        <div className="break-words text-sm">
          <ChatMarkdown>{message.content}</ChatMarkdown>
        </div>
      )}
      {message.toolCalls?.map((call) => (
        <div key={call.id} className="space-y-1.5">
          <ToolCallCard
            call={call}
            showUndo={isLastAssistant && canUndo}
            onUndo={onUndo}
            boardVisible={isBoardVisible(call.id)}
            onToggleBoard={() => onToggleBoard(call.id)}
          />
          {renderToolCallSupplement?.(call)}
        </div>
      ))}
      {message.warnings && message.warnings.length > 0 && (
        <div className="space-y-1">
          {message.warnings.map((w, i) => (
            <Alert key={i} className="py-1.5 text-xs">
              <AlertCircle className="h-3 w-3" />
              <AlertDescription>{w}</AlertDescription>
            </Alert>
          ))}
        </div>
      )}
    </div>
  );
}

function ToolCallCard({
  call,
  showUndo,
  onUndo,
  boardVisible,
  onToggleBoard,
}: {
  call: ToolCallDisplay;
  showUndo: boolean;
  onUndo: () => void;
  boardVisible: boolean;
  onToggleBoard: () => void;
}) {
  const deviceType = call.deviceType ?? "flagship";
  const hasBoard = !!call.appliedSnapshot;
  return (
    <div className="space-y-2 rounded-lg border bg-muted/40 p-2.5">
      <div className="flex items-center justify-between gap-2">
        <Badge variant="secondary" className="font-mono text-[10px]">
          {labelFor(call)}
        </Badge>
        <div className="flex items-center gap-1">
          {hasBoard && !boardVisible && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 gap-1 px-1.5 text-[11px] text-muted-foreground"
              onClick={onToggleBoard}
              title="Show board preview"
            >
              <Eye className="h-3 w-3" />
              Show board
            </Button>
          )}
          {hasBoard && boardVisible && !showUndo && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 gap-1 px-1.5 text-[11px] text-muted-foreground"
              onClick={onToggleBoard}
              title="Hide board preview"
            >
              <EyeOff className="h-3 w-3" />
            </Button>
          )}
          {showUndo && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 gap-1 px-1.5 text-[11px]"
              onClick={onUndo}
              title="Undo last AI change"
            >
              <Undo2 className="h-3 w-3" />
              Undo
            </Button>
          )}
        </div>
      </div>
      {hasBoard && boardVisible && (
        <InlineBoardPreview
          snapshot={call.appliedSnapshot!}
          deviceType={deviceType}
        />
      )}
      <ToolCallSummary call={call} />
    </div>
  );
}

function labelFor(call: ToolCall): string {
  switch (call.op) {
    case "replace_page":
      return "Replaced page";
    case "apply_patch":
      return `Applied ${call.args.changes.length} change${call.args.changes.length === 1 ? "" : "s"}`;
    case "suggest_variables":
      return `${call.args.suggestions.length} suggestion${call.args.suggestions.length === 1 ? "" : "s"}`;
    case "navigate_to_page":
      return call.args.page_id === "new" ? "New page" : "Navigate to page";
    case "install_plugin":
      return `Install: ${call.args.plugin_id}`;
    case "update_plugin_config":
      return `Configure: ${call.args.plugin_id}`;
    case "update_plugin":
      return `Update: ${call.args.plugin_id}`;
    case "update_setting":
      return `Setting: ${call.args.category}`;
    case "create_carousel":
      return `Create carousel: "${call.args.name}"`;
    case "update_carousel":
      return "Update carousel";
    case "create_schedule":
      return `Schedule: ${call.args.start_time}${call.args.end_time ? `–${call.args.end_time}` : "+"}`;
    case "update_schedule":
      return "Update schedule";
    case "delete_schedule":
      return "Delete schedule";
    case "trigger_system_update":
      return "System update";
  }
}

function ToolCallSummary({ call }: { call: ToolCall }) {
  // `replace_page` is fully described by the inline board preview
  // above; rendering a JSON line-dump here would just duplicate the
  // visual. Keep the card lean.
  if (call.op === "replace_page") {
    return null;
  }
  if (call.op === "apply_patch") {
    const count = call.args.changes.length + (call.args.rename ? 1 : 0);
    return (
      // Patches with long color-token strings can dominate the card —
      // hide the raw line text behind a disclosure so the preview is
      // the main thing the user sees, with the patch detail
      // available for anyone who wants to inspect it.
      <PatchDetailDisclosure count={count}>
        <ul className="space-y-0.5 px-1 pt-1 text-[11px] text-muted-foreground">
          {call.args.changes.map((c, i) => (
            <li key={i} className="break-all font-mono">
              {summarizeLineOp(c)}
            </li>
          ))}
          {call.args.rename && (
            <li className="break-all font-mono">
              → rename to "{call.args.rename}"
            </li>
          )}
        </ul>
      </PatchDetailDisclosure>
    );
  }
  if (call.op === "suggest_variables") {
    return (
      <ul className="space-y-0.5 text-[11px]">
        {call.args.suggestions.map((s, i) => (
          <li key={i}>
            <code className="font-mono text-[10px]">{`{{${s.ref}}}`}</code>
            {s.description && (
              <span className="text-muted-foreground"> — {s.description}</span>
            )}
          </li>
        ))}
      </ul>
    );
  }
  // navigate_to_page, install_plugin, update_plugin_config, update_setting:
  // these are handled by renderToolCallSupplement (AiActionConfirmation).
  return null;
}

function PatchDetailDisclosure({
  count,
  children,
}: {
  count: number;
  children: React.ReactNode;
}) {
  return (
    <Collapsible className="text-[11px]">
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="group/disclose flex w-full items-center gap-1 rounded text-[10px] text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronRight className="h-3 w-3 transition-transform group-data-[state=open]/disclose:rotate-90" />
          <span>
            {count === 1 ? "View change" : `View ${count} changes`}
          </span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  );
}

function summarizeLineOp(op: LineOp): string {
  switch (op.type) {
    case "replace_line":
      return `line ${op.index + 1}: "${op.text}"`;
    case "insert_line":
      return `+ line ${op.index + 1}: "${op.text}"`;
    case "delete_line":
      return `− line ${op.index + 1}`;
    case "update_line_metadata": {
      const parts: string[] = [];
      if (op.alignment) parts.push(op.alignment);
      if (op.wrap !== undefined) parts.push(`wrap=${op.wrap}`);
      return `line ${op.index + 1} meta: ${parts.join(" ")}`;
    }
  }
}
