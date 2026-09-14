"use client";

import { Button, Card, Flex, Suggestion, Suggestions, Text } from "@fiestaboard/ui";
import { MessageCircleQuestion } from "lucide-react";

import { useTranslations } from "@/i18n/translations";
import type { Elicitation, ElicitationAnswer } from "@/lib/ai-chat-types";

export interface AiQuestionCardProps {
  elicitation: Elicitation & { answer?: ElicitationAnswer };
  onAnswer: (answer: ElicitationAnswer) => void;
  /** True while the resume request is in flight. */
  busy?: boolean;
}

/**
 * The assistant asked something (`ask_user`, shaped like an MCP
 * elicitation). Options render as one-click chips; a free-text answer goes
 * through the composer, which the panel retargets while a question is
 * pending. Once answered, the card collapses to what was said.
 */
export function AiQuestionCard({ elicitation, onAnswer, busy = false }: AiQuestionCardProps) {
  const t = useTranslations("aiChatPanel");
  const answerProp = elicitation.requested_schema.properties.answer;
  const options = answerProp?.enum ?? [];
  const answered = elicitation.answer;

  if (answered) {
    const said =
      answered.action === "accept"
        ? String(answered.content.answer ?? Object.values(answered.content)[0] ?? "")
        : answered.action === "decline"
          ? t("question.declined")
          : t("question.cancelled");
    return (
      <Text size="xs" tone="muted" data-testid="ai-question-answered">
        {t("question.answered", { answer: said })}
      </Text>
    );
  }

  return (
    <Card data-testid="ai-question-card" role="group" aria-label={elicitation.message} className="gap-2 px-3 py-3">
      <Flex align="start" gap="2">
        <MessageCircleQuestion className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
        <Text size="sm">{elicitation.message}</Text>
      </Flex>
      {options.length > 0 ? (
        <Suggestions>
          {options.map((option) => (
            <Suggestion
              key={option}
              suggestion={option}
              disabled={busy}
              onClick={(value) => onAnswer({ action: "accept", content: { answer: value } })}
            />
          ))}
        </Suggestions>
      ) : null}
      <Flex align="center" justify="between" gap="2">
        <Text size="xs" tone="muted">
          {elicitation.allow_free_text ? t("question.typeAnswer") : ""}
        </Text>
        <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => onAnswer({ action: "decline" })}>
          {t("question.skip")}
        </Button>
      </Flex>
    </Card>
  );
}
