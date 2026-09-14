"use client";

import { Box, Shimmer, Task, TaskContent, TaskItem, TaskTrigger } from "@fiestaboard/ui";

import { detailForTool, labelForTool } from "@/components/ai-tool-labels";
import { useTranslations } from "@/i18n/translations";
import type { ChatMessage, ToolPhase } from "@/lib/ai-chat-types";

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

/**
 * The observed steps of the current turn: one row per tool call the
 * server actually made, plus the server's own status line while it works.
 * Nothing here is the model's self-report — every row is a `tool_call`
 * frame, every tick a `tool_result`.
 *
 * Rendered OUTSIDE the conversation's live region so each step is
 * announced once, by this `role="status"` box, not again by the log.
 */
export function AiStepTimeline({ message }: { message: ChatMessage }) {
  const t = useTranslations("aiChatPanel");
  const calls = message.toolCalls ?? [];
  const doneCount = calls.filter((c) => c.phase === "ok").length;

  if (calls.length === 0 && !message.statusMessage) return null;

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
        <Task className="border-0 bg-transparent">
          <TaskTrigger title={t("stepsHeading", { done: doneCount, total: calls.length })} className="px-1 py-1" />
          <TaskContent className="border-0 px-1 pb-1 pt-0">
            {calls.map((call) => {
              const detail = detailForTool(call);
              return (
                <TaskItem key={call.id} status={STATUS_FOR_PHASE[call.phase]}>
                  {labelForTool(call, t)}
                  {detail ? ` · ${detail}` : ""}
                </TaskItem>
              );
            })}
          </TaskContent>
        </Task>
      ) : null}
      {message.pending && message.statusMessage ? (
        <Shimmer className="block px-1 pt-1 text-xs">{message.statusMessage}</Shimmer>
      ) : null}
    </Box>
  );
}
