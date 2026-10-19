"use client";

import { Box, Spinner, Task, TaskContent, TaskTrigger, Text } from "@fiestaboard/ui";
import { Check, CirclePause, CircleSlash, MessageCircleQuestion, ShieldCheck, TriangleAlert } from "lucide-react";

import { labelForTool } from "@/components/ai-tool-labels";
import { useTranslations } from "@/i18n/translations";
import { deriveChatActivity } from "@/lib/ai-chat-activity";
import type { ChatMessage } from "@/lib/ai-chat-types";
import { parseToolDraft } from "@/lib/ai-choreography/draft";
import type { ChatStatus } from "@/lib/use-ai-chat";

/** Entries since the user last spoke, including resumes of the same turn. */
export function currentTurnEntries(messages: ChatMessage[]): ChatMessage[] {
  let start = messages.length;
  while (start > 0 && messages[start - 1].role === "assistant") start -= 1;
  return messages.slice(start);
}

/** One disclosure for observed activity; its children are chronological detail rows. */
export function AiTurnActivity({
  entries,
  status,
  error,
  pausedAtLimit = false,
  readOnly = false,
  children,
}: {
  entries: ChatMessage[];
  status: ChatStatus;
  error?: string | null;
  pausedAtLimit?: boolean;
  readOnly?: boolean;
  children?: React.ReactNode;
}) {
  const t = useTranslations("aiChatPanel");
  const activity = deriveChatActivity(entries, status, error, pausedAtLimit);
  const calls = entries.flatMap((entry) => entry.toolCalls ?? []).filter((call) => call.name !== "ask_user");
  const doneCount = calls.filter((call) => call.phase === "ok").length;
  const moving = !readOnly && ["thinking", "preparing", "running", "writing"].includes(activity.state);
  const Icon =
    activity.state === "approval"
      ? ShieldCheck
      : activity.state === "input"
        ? MessageCircleQuestion
        : activity.state === "error"
          ? TriangleAlert
          : activity.state === "denied"
            ? CircleSlash
            : activity.state === "stopped" || activity.state === "paused"
              ? CirclePause
              : Check;
  const draft = entries.at(-1)?.draft;
  const draftName = draft ? (draft.op ?? parseToolDraft(draft.text).name) : null;
  const label =
    activity.state === "running" && activity.tool
      ? t("status.running", { tool: labelForTool(activity.tool, t) })
      : activity.state === "preparing" && draftName
        ? t("status.preparing", { tool: labelForTool({ name: draftName, title: draftName }, t) })
        : t(`activity.${activity.state}`);
  const title = (
    <Text as="span" className="flex min-w-0 items-center gap-2">
      {moving ? <Spinner size="sm" label={null} /> : <Icon className="size-3.5 shrink-0" aria-hidden="true" />}
      <Text as="span" className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <Text as="span" size="xs" weight="medium" className="min-w-0 break-words">
          {label}
        </Text>
        {doneCount > 0 ? (
          <Text as="span" size="xs" tone="muted" className="min-w-0 break-words">
            {t("activity.completedActions", { count: doneCount })}
          </Text>
        ) : null}
      </Text>
    </Text>
  );
  return (
    <Box data-testid="ai-turn-activity" data-activity={activity.state} className="fiestabot-activity min-w-0">
      {children ? (
        <Task defaultOpen={false}>
          <TaskTrigger title={title} className="fiestabot-activity-heading" />
          <TaskContent data-testid="ai-activity-details" aria-label={t("activity.details")}>
            {children}
          </TaskContent>
        </Task>
      ) : (
        <Box className="py-1 text-brand-emphasis">{title}</Box>
      )}
    </Box>
  );
}
