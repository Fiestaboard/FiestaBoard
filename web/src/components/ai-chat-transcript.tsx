"use client";

import {
  Alert,
  AlertDescription,
  Box,
  Flex,
  Message,
  MessageContent,
  Stack,
  Text,
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
  type ToolState,
} from "@fiestaboard/ui";
import { AlertCircle, Sparkles } from "lucide-react";
import { memo, useMemo } from "react";

import { AiApprovalCard } from "@/components/ai-approval-card";
import { AiAutoApprovedBadge } from "@/components/ai-auto-approved-badge";
import { AiQuestionCard } from "@/components/ai-question-card";
import { AiToolArguments, AiToolResultSummary } from "@/components/ai-tool-detail";
import { labelForTool } from "@/components/ai-tool-labels";
import { AiToolRun, groupToolCalls } from "@/components/ai-tool-runs";
import { ChatMarkdown } from "@/components/chat-markdown";
import { InlineBoardPreview } from "@/components/inline-board-preview";
import { useToolDetail } from "@/hooks/use-target-caches";
import { useLocale, useTranslations } from "@/i18n/translations";
import type {
  ApprovalDecision,
  ChatMessage,
  Elicitation,
  ElicitationAnswer,
  SSEToolStreamingData,
  ToolCall,
  ToolCallDisplay,
  ToolPhase,
} from "@/lib/ai-chat-types";
import { parseToolDraft } from "@/lib/ai-choreography/draft";
import { formatRelativeTime } from "@/lib/relative-time";
import type { ApproveOptions } from "@/lib/use-ai-chat";

// The transcript as the panel draws it: user turns, assistant turns (one
// per model call, grouped), tool cards, questions. Shared between the live
// chat and the read-only review of a saved conversation (#2022), which is
// why it lives apart from the panel's chrome and composer.

export type Turn =
  { role: "user"; index: number; message: ChatMessage } | { role: "assistant"; index: number; entries: ChatMessage[] };

/** Pure: consecutive assistant entries become one turn; `index` is the first entry's. */
export function groupTurns(messages: ChatMessage[]): Turn[] {
  const turns: Turn[] = [];
  messages.forEach((m, index) => {
    const last = turns[turns.length - 1];
    if (m.role === "user") {
      turns.push({ role: "user", index, message: m });
    } else if (last?.role === "assistant") {
      last.entries.push(m);
    } else {
      turns.push({ role: "assistant", index, entries: [m] });
    }
  });
  return turns;
}

export interface TranscriptTurnsProps {
  turns: Turn[];
  /** The destructive call the turn is paused on, if any (live chat only). */
  pendingApproval: ToolCall | null;
  /** The question the turn is paused on, if any (live chat only). */
  pendingElicitation: Elicitation | null;
  busy: boolean;
  onApprove: (id: string, decision: ApprovalDecision, options?: ApproveOptions) => void;
  onAnswer: (id: string, answer: ElicitationAnswer) => void;
}

const noDecision = () => {};

/**
 * The turns of a transcript. For a read-only view pass `pendingApproval` /
 * `pendingElicitation` as null and `busy` true: no card offers a decision.
 */
export function TranscriptTurns({
  turns,
  pendingApproval,
  pendingElicitation,
  busy,
  onApprove,
  onAnswer,
}: TranscriptTurnsProps) {
  return (
    <>
      {turns.map((turn, i) =>
        turn.role === "user" ? (
          <Message key={turn.index} from="user">
            {/* 92%, not the primitive's 85%: with the assistant's avatar
                gutter gone the column is wider, and a hard 85% left a ragged
                margin on the one element that is meant to hug the right. */}
            <MessageContent className="max-w-[92%] whitespace-pre-wrap break-words">
              {turn.message.content}
            </MessageContent>
          </Message>
        ) : (
          <AssistantTurn
            key={turn.index}
            entries={turn.entries}
            isLast={i === turns.length - 1}
            pendingApproval={pendingApproval}
            pendingElicitation={pendingElicitation}
            busy={busy}
            onApprove={onApprove}
            onAnswer={onAnswer}
          />
        ),
      )}
    </>
  );
}

/** A saved conversation as it looked: every card settled, nothing to decide. */
export function ReadOnlyTranscript({ messages }: { messages: ChatMessage[] }) {
  return (
    <TranscriptTurns
      turns={groupTurns(messages)}
      pendingApproval={null}
      pendingElicitation={null}
      busy
      onApprove={noDecision}
      onAnswer={noDecision}
    />
  );
}

function AssistantTurn({
  entries,
  isLast,
  pendingApproval,
  pendingElicitation,
  busy,
  onApprove,
  onAnswer,
}: {
  entries: ChatMessage[];
  isLast: boolean;
  pendingApproval: ToolCall | null;
  pendingElicitation: Elicitation | null;
  busy: boolean;
  onApprove: (id: string, decision: ApprovalDecision, options?: ApproveOptions) => void;
  onAnswer: (id: string, answer: ElicitationAnswer) => void;
}) {
  return (
    <Message from="assistant">
      <MessageContent>
        <Stack gap="2">
          <AssistantByline at={entries[0]?.at} />
          {entries.map((message, i) => {
            const isLastEntry = isLast && i === entries.length - 1;
            return (
              <AssistantEntry
                key={i}
                message={message}
                isLastEntry={isLastEntry}
                pendingApproval={isLastEntry ? pendingApproval : null}
                pendingElicitation={isLastEntry ? pendingElicitation : null}
                busy={isLastEntry ? busy : false}
                onApprove={onApprove}
                onAnswer={onAnswer}
              />
            );
          })}
        </Stack>
      </MessageContent>
    </Message>
  );
}

/**
 * Who is speaking, once per run of assistant entries.
 *
 * The avatar this replaces was a 32px gutter down the whole turn, which is
 * what pushed tool cards, board previews and the approval card into ~85% of
 * an already narrow drawer. A byline says the same thing in one 20px row
 * and gives the work the full column. Four tool calls and the sentence that
 * follows them are one piece of work, so they get one byline, not five.
 */
function AssistantByline({ at }: { at?: string }) {
  const t = useTranslations("aiChatPanel");
  const locale = useLocale();
  return (
    <Flex align="center" gap="1.5" className="h-5 min-w-0" data-testid="ai-assistant-byline">
      <Sparkles className="size-3.5 shrink-0 text-brand-emphasis" aria-hidden="true" />
      <Text as="span" size="xs" tone="muted" weight="medium">
        {t("panelTitle")}
      </Text>
      {at ? (
        <Text as="span" size="xs" tone="muted" className="truncate">
          {`· ${formatRelativeTime(at, locale)}`}
        </Text>
      ) : null}
    </Flex>
  );
}

/**
 * One model call's output. Memoised so a streamed delta re-renders only the
 * entry it lands in: `patchLastAssistant` keeps every other entry's object
 * identity, and the pending/busy props are only ever non-empty for the
 * last entry.
 */
const AssistantEntry = memo(function AssistantEntry({
  message,
  isLastEntry,
  pendingApproval,
  pendingElicitation,
  busy,
  onApprove,
  onAnswer,
}: {
  message: ChatMessage;
  isLastEntry: boolean;
  pendingApproval: ToolCall | null;
  pendingElicitation: Elicitation | null;
  busy: boolean;
  onApprove: (id: string, decision: ApprovalDecision, options?: ApproveOptions) => void;
  onAnswer: (id: string, answer: ElicitationAnswer) => void;
}) {
  return (
    <Stack gap="2">
      {message.content && (
        <Box className="break-words text-sm">
          <ChatMarkdown>{message.content}</ChatMarkdown>
        </Box>
      )}
      {groupToolCalls((message.toolCalls ?? []).filter((call) => call.name !== "ask_user")).map((group) =>
        group.kind === "run" ? (
          <AiToolRun key={group.calls[0].id} group={group}>
            {group.calls.map((call) => (
              <ToolCallCard key={call.id} call={call} />
            ))}
          </AiToolRun>
        ) : (
          <Stack key={group.call.id} gap="1.5">
            <ToolCallCard call={group.call} />
            {isLastEntry && pendingApproval?.id === group.call.id && group.call.phase === "awaiting_approval" ? (
              <AiApprovalCard
                call={group.call}
                busy={busy}
                onApprove={() => onApprove(group.call.id, "approve")}
                onDeny={() => onApprove(group.call.id, "deny")}
                onApproveAll={() => onApprove(group.call.id, "approve", { autoApproveConversation: true })}
              />
            ) : null}
          </Stack>
        ),
      )}
      {message.draft ? <DraftToolCard draft={message.draft} /> : null}
      {message.elicitation ? (
        <AiQuestionCard
          elicitation={message.elicitation}
          busy={busy || (isLastEntry && pendingElicitation === null && !message.elicitation.answer)}
          onAnswer={(a) => onAnswer(message.elicitation!.id, a)}
        />
      ) : null}
      {message.warnings && message.warnings.length > 0 && (
        <Stack gap="1">
          {message.warnings.map((w, j) => (
            <Alert key={j} className="py-1.5 text-xs">
              <AlertCircle className="h-3 w-3" />
              <AlertDescription>{w}</AlertDescription>
            </Alert>
          ))}
        </Stack>
      )}
    </Stack>
  );
});

/**
 * The tool block the model is still writing, as a card in the
 * `input-streaming` state with whatever arguments can be read so far — so a
 * six-line page is visible as it is composed, not only once it closes.
 */
function DraftToolCard({ draft }: { draft: SSEToolStreamingData }) {
  const t = useTranslations("aiChatPanel");
  const parsed = useMemo(() => parseToolDraft(draft.text), [draft.text]);
  const name = draft.op ?? parsed.name;
  const input: Record<string, unknown> = { ...parsed.strings, ...parsed.lists };
  if (parsed.partial) {
    const { key, index, value } = parsed.partial;
    if (index === undefined) input[key] = value + "…";
    else input[key] = [...((input[key] as string[] | undefined) ?? []), value + "…"];
  }
  const label = name ? labelForTool({ ...DRAFT_CALL, name, title: name }, t) : t("status.thinking");
  return (
    <Tool
      state="input-streaming"
      data-testid="ai-tool-draft"
      labels={{
        input: t("toolInput"),
        output: t("toolOutput"),
        states: { "input-streaming": t("toolStates.inputStreaming") },
      }}
    >
      <ToolHeader title={label} />
      <ToolContent>{Object.keys(input).length > 0 ? <ToolInput input={input} /> : null}</ToolContent>
    </Tool>
  );
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
  const detail = useToolDetail(call);
  const deviceType = call.deviceType ?? "flagship";
  const state = TOOL_STATE_FOR_PHASE[call.phase];
  const result = call.result;
  // The server's `summary` is English prose for logs; the card shows the
  // result itself (and the board preview a page tool implies), so nothing
  // untranslated reaches the screen. Error text is the executor's own
  // message, as everywhere else in the app.
  const errorText =
    result && (result.status === "error" || result.status === "blocked") ? (result.error ?? undefined) : undefined;
  const preview = call.appliedSnapshot ? (
    <InlineBoardPreview snapshot={call.appliedSnapshot} deviceType={deviceType} />
  ) : null;
  const hasResult = result?.status === "ok" && result.result !== null && result.result !== undefined;
  const output =
    preview || hasResult ? (
      <Stack gap="2">
        {preview}
        {hasResult ? <AiToolResultSummary result={result.result} /> : null}
      </Stack>
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
      {/* Title and detail are composed here rather than passed as the
          primitive's two strings, and they WRAP. The primitive puts both on
          one truncating line, which at drawer width cut the interesting half
          off every card ("Add schedule 07:00–09…", #2024) — and cut the
          label instead once the detail became a real name. Two lines in a
          384px drawer beat one line that says "Add sched… Goodnight · 21:0…". */}
      <ToolHeader
        title={
          <Text
            as="span"
            className="inline-flex min-w-0 max-w-full flex-wrap items-baseline gap-x-1.5 whitespace-normal"
          >
            <Text as="span" className="shrink-0">
              {labelForTool(call, t)}
            </Text>
            {detail ? (
              <Text as="span" tone="muted" className="min-w-0 break-words font-normal">
                {detail}
              </Text>
            ) : null}
            {call.auto_approved ? <AiAutoApprovedBadge interactive={false} /> : null}
          </Text>
        }
      />
      <ToolContent>
        <AiToolArguments call={call} />
        <ToolOutput output={output} errorText={errorText} />
      </ToolContent>
    </Tool>
  );
}
