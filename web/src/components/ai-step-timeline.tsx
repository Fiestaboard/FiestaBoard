"use client";

import { Box, Shimmer, Task, TaskContent, TaskItem, TaskTrigger } from "@fiestaboard/ui";
import { useEffect, useState } from "react";

import { detailForTool, labelForTool, type TranslateFn } from "@/components/ai-tool-labels";
import { useTranslations } from "@/i18n/translations";
import type { ChatMessage, ToolCall, ToolPhase } from "@/lib/ai-chat-types";
import { parseToolDraft } from "@/lib/ai-choreography/draft";
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
  const seconds = useElapsedSeconds(Boolean(last?.pending));
  const statusLine = last?.pending ? statusText(last, messages, seconds, t) : null;

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
      {statusLine ? <Shimmer className="block px-1 pt-1 text-xs">{statusLine}</Shimmer> : null}
    </Box>
  );
}

/**
 * The status line, from the frame's phase and tool id — never its English
 * `message`. While the model writes a tool block the line names that tool;
 * a long think shows how long it has been thinking, so the wait is never a
 * black box.
 */
function statusText(entry: ChatMessage, messages: ChatMessage[], seconds: number, t: TranslateFn): string | null {
  const suffix = seconds >= 3 ? ` · ${t("status.elapsed", { seconds })}` : "";
  if (entry.draft) {
    const parsed = parseToolDraft(entry.draft.text);
    const name = entry.draft.op ?? parsed.name;
    const tool = name ? labelForTool({ ...DRAFT_CALL, name, title: name }, t) : "";
    return name ? t("status.preparing", { tool }) + suffix : t("status.thinking") + suffix;
  }
  const status = entry.status;
  if (!status) return entry.pending ? t("status.thinking") + suffix : null;
  if (status.phase === "thinking") return t("status.thinking") + suffix;
  // The call may sit in an earlier entry (an approved call is resumed from
  // the entry that proposed it), so look across the whole transcript.
  const call = status.toolCallId ? findCall(messages, status.toolCallId) : undefined;
  const tool = call ? labelForTool(call, t) : "";
  return t("status.running", { tool });
}

/** Whole seconds since `active` became true; 0 while inactive. */
function useElapsedSeconds(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    const started = Date.now();
    // The first tick resets the count for this wait; later ticks count up.
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    const reset = window.setTimeout(() => setSeconds(0), 0);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(reset);
    };
  }, [active]);
  return active ? seconds : 0;
}

const DRAFT_CALL: ToolCall = {
  id: "draft",
  name: "",
  args: {},
  title: "",
  read_only: false,
  destructive: false,
  requires_approval: false,
  source: "mcp",
};
