"use client";

import { Stack, Text, Tool, ToolContent, ToolHeader } from "@fiestaboard/ui";

import { labelForTool, type TranslateFn } from "@/components/ai-tool-labels";
import { useTranslations } from "@/i18n/translations";
import type { ToolCallDisplay } from "@/lib/ai-chat-types";

// A run of the same action, as one row.
//
// "Set up my daily schedule" is four create_schedule calls, and since the
// card headers wrap (#2024 finding 11) that is eight lines of chrome before
// the sentence that explains them. Consecutive successful calls of the same
// tool collapse into one row that opens to the very same cards.
//
// What is never collapsed: anything that failed, anything the user denied,
// anything still running, and anything that was gated on their approval —
// even when it succeeded. Those are the rows a person needs to see happened,
// so they stay cards in their own right. A run of one is not a run.

export type ToolCallGroup =
  { kind: "single"; call: ToolCallDisplay } | { kind: "run"; name: string; calls: ToolCallDisplay[] };

/** Only a settled, ungated success can disappear into a run. */
function groupable(call: ToolCallDisplay): boolean {
  return call.phase === "ok" && !call.requires_approval;
}

/** Consecutive same-tool successes become runs; everything else stays itself. */
export function groupToolCalls(calls: ToolCallDisplay[]): ToolCallGroup[] {
  const groups: ToolCallGroup[] = [];

  for (const call of calls) {
    const last = groups[groups.length - 1];
    if (!groupable(call)) {
      groups.push({ kind: "single", call });
      continue;
    }
    if (last?.kind === "run" && last.name === call.name) {
      last.calls.push(call);
      continue;
    }
    if (last?.kind === "single" && last.call.name === call.name && groupable(last.call)) {
      groups[groups.length - 1] = { kind: "run", name: call.name, calls: [last.call, call] };
      continue;
    }
    groups.push({ kind: "single", call });
  }

  return groups;
}

/** "Add schedule · 4 times" — the label the cards already use, plus the count. */
export function runSummary(group: Extract<ToolCallGroup, { kind: "run" }>, t: TranslateFn): string {
  const first = group.calls[0];
  return t("toolRun", { tool: labelForTool(first, t), count: group.calls.length });
}

/**
 * The collapsed row. Open it and the individual cards are exactly the cards
 * they would have been — this hides nothing, it only stops four of them
 * taking eight lines before anyone has read the reply.
 */
export function AiToolRun({
  group,
  children,
}: {
  group: Extract<ToolCallGroup, { kind: "run" }>;
  children: React.ReactNode;
}) {
  const t = useTranslations("aiChatPanel");
  return (
    <Tool
      state="output-available"
      data-testid={`ai-tool-run-${group.name}`}
      labels={{
        input: t("toolInput"),
        output: t("toolOutput"),
        states: { "output-available": t("toolStates.outputAvailable") },
      }}
    >
      <ToolHeader
        title={
          <Text as="span" className="min-w-0 truncate">
            {runSummary(group, t)}
          </Text>
        }
      />
      <ToolContent>
        <Stack gap="1.5">{children}</Stack>
      </ToolContent>
    </Tool>
  );
}
