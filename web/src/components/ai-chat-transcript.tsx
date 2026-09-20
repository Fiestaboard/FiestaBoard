"use client";

import {
  Alert,
  AlertDescription,
  Box,
  JsonTree,
  Message,
  MessageAvatar,
  MessageContent,
  Stack,
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
  type ToolState,
} from "@fiestaboard/ui";
import { AlertCircle, Sparkles } from "lucide-react";
import { memo } from "react";

import { AiApprovalCard } from "@/components/ai-approval-card";
import { AiAutoApprovedBadge } from "@/components/ai-auto-approved-badge";
import { AiQuestionCard } from "@/components/ai-question-card";
import { detailForTool, labelForTool } from "@/components/ai-tool-labels";
import { ChatMarkdown } from "@/components/chat-markdown";
import { InlineBoardPreview } from "@/components/inline-board-preview";
import { useTranslations } from "@/i18n/translations";
import type {
  ApprovalDecision,
  ChatMessage,
  Elicitation,
  ElicitationAnswer,
  ToolCall,
  ToolCallDisplay,
  ToolPhase,
} from "@/lib/ai-chat-types";
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
            <MessageContent className="whitespace-pre-wrap break-words">{turn.message.content}</MessageContent>
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
      <MessageAvatar>
        <Sparkles />
      </MessageAvatar>
      <MessageContent>
        <Stack gap="2">
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
      {message.toolCalls
        ?.filter((call) => call.name !== "ask_user")
        .map((call) => (
          <Stack key={call.id} gap="1.5">
            <ToolCallCard call={call} />
            {isLastEntry && pendingApproval?.id === call.id && call.phase === "awaiting_approval" ? (
              <AiApprovalCard
                call={call}
                busy={busy}
                onApprove={() => onApprove(call.id, "approve")}
                onDeny={() => onApprove(call.id, "deny")}
                onApproveAll={() => onApprove(call.id, "approve", { autoApproveConversation: true })}
              />
            ) : null}
          </Stack>
        ))}
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
        {hasResult ? (
          <Box
            className="max-h-48 overflow-auto rounded-md bg-muted p-2 font-mono text-xs"
            data-testid="ai-tool-result"
          >
            <JsonTree data={result.result} />
          </Box>
        ) : null}
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
      <ToolHeader
        title={labelForTool(call, t)}
        detail={
          call.auto_approved ? (
            <>
              {detailForTool(call)}
              <AiAutoApprovedBadge interactive={false} />
            </>
          ) : (
            detailForTool(call)
          )
        }
      />
      <ToolContent>
        <ToolInput input={call.args} />
        <ToolOutput output={output} errorText={errorText} />
      </ToolContent>
    </Tool>
  );
}
