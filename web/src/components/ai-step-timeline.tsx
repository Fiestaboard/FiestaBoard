"use client";

import {
  Badge,
  Box,
  Shimmer,
  Task,
  TaskContent,
  TaskItem,
  TaskTrigger,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@fiestaboard/ui";

import { detailForTool, labelForTool, type TranslateFn } from "@/components/ai-tool-labels";
import { useTranslations } from "@/i18n/translations";
import type { ChatMessage, ToolPhase, TurnStatus } from "@/lib/ai-chat-types";
import { findCall } from "@/lib/use-ai-chat";

type ItemStatus = "pending" | "running" | "done" | "error";

const STATUS_FOR_PHASE: Record<ToolPhase, ItemStatus> = {
  running: "running",
  awaiting_approval: "running",
  ok: "done",
  blocked: "error",
  error: "error",
  denied: "error",
  stopped: "error",
};

/** The entries since the user last spoke: one per model call, a resume starts another. */
export function currentTurnEntries(messages: ChatMessage[]): ChatMessage[] {
  let start = messages.length;
  while (start > 0 && messages[start - 1].role === "assistant") start -= 1;
  return messages.slice(start);
}

/**
 * The observed steps of the current turn: one row per tool call the
 * server actually made, plus a status line while it works. Nothing here
 * is the model's self-report — every row is a `tool_call` frame, every
 * tick a `tool_result`.
 *
 * The status line is rendered from the frame's `phase` and tool id, not
 * its English `message`, so it reads in the user's language.
 *
 * Rendered OUTSIDE the conversation's live region so each step is
 * announced once, by this `role="status"` box, not again by the log.
 */
export function AiStepTimeline({ messages }: { messages: ChatMessage[] }) {
  const t = useTranslations("aiChatPanel");
  const entries = currentTurnEntries(messages);
  // A question is answered by the person, not run by the server; its card
  // is the question itself, so it is not a step here.
  const calls = entries.flatMap((m) => m.toolCalls ?? []).filter((c) => c.name !== "ask_user");
  const last = entries[entries.length - 1];
  const doneCount = calls.filter((c) => c.phase === "ok").length;
  const statusLine = last?.pending && last.status ? statusText(last.status, messages, t) : null;

  if (calls.length === 0 && !statusLine) return null;

  return (
    <Box
      role="status"
      aria-live="polite"
      aria-atomic="false"
      aria-label={t("stepsAriaLabel")}
      className="flex-shrink-0 border-b bg-muted/30 px-3 py-2"
      data-testid="ai-step-timeline"
    >
      {calls.length > 0 ? (
        <TooltipProvider>
          <Task className="border-0 bg-transparent">
            <TaskTrigger title={t("stepsHeading", { done: doneCount, total: calls.length })} className="px-1 py-1" />
            <TaskContent className="border-0 px-1 pb-1 pt-0">
              {calls.map((call) => {
                const detail = detailForTool(call);
                return (
                  <TaskItem key={call.id} status={STATUS_FOR_PHASE[call.phase]}>
                    {labelForTool(call, t)}
                    {detail ? ` · ${detail}` : ""}
                    {call.auto_approved ? <AutoApprovedBadge t={t} /> : null}
                  </TaskItem>
                );
              })}
            </TaskContent>
          </Task>
        </TooltipProvider>
      ) : null}
      {statusLine ? <Shimmer className="block px-1 pt-1 text-xs">{statusLine}</Shimmer> : null}
    </Box>
  );
}

/**
 * A destructive call that ran without a pause — the install is in Auto, or
 * the user chose "don't ask again" for this chat. The badge is focusable so
 * the tooltip opens from the keyboard too; its accessible name is the full
 * explanation, not the three-letter glyph.
 */
function AutoApprovedBadge({ t }: { t: TranslateFn }) {
  const tooltip = t("autoApproved.tooltip");
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          tabIndex={0}
          aria-label={tooltip}
          data-testid="ai-auto-approved-badge"
          className="ml-1.5 px-1 py-0 text-[10px] uppercase tracking-wide"
        >
          {t("autoApproved.badge")}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}

function statusText(status: TurnStatus, messages: ChatMessage[], t: TranslateFn): string {
  if (status.phase === "thinking") return t("status.thinking");
  // The call may sit in an earlier entry (an approved call is resumed from
  // the entry that proposed it), so look across the whole transcript.
  const call = status.toolCallId ? findCall(messages, status.toolCallId) : undefined;
  const tool = call ? labelForTool(call, t) : "";
  return t("status.running", { tool });
}
