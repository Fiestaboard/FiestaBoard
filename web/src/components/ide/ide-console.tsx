"use client";

import {
  Box,
  Button,
  Flex,
  ProblemItem,
  SentLog,
  Stack,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Text,
} from "@fiestaboard/ui";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useMemo } from "react";

import { useTranslations } from "@/i18n/translations";
import { useFormatEditTime } from "@/lib/edit-time";
import { jumpToTemplateLine } from "@/lib/ide/jump-to-line";
import type { IdeProblem } from "@/lib/ide/problems";
import { problemTitleParts, substitutionSummary } from "@/lib/ide/problems";
import { sendLogModel } from "@/lib/ide/sends";

import type { CreatorIdeState } from "./use-creator-ide";

export type ConsoleTab = "problems" | "warnings" | "sent";

/** One problem as C44 ProblemItem; Jump to source moves the editor caret. */
export function IdeProblemList({
  problems,
  emptyLabel,
  layout,
  size,
}: {
  problems: readonly IdeProblem[];
  emptyLabel: string;
  layout: "inline" | "stacked";
  size?: "default" | "touch";
}) {
  const t = useTranslations("creatorIde");
  const tc = useTranslations("complexEditing");
  if (!problems.length) {
    return (
      <Text size="sm" tone="muted" data-slot="ide-problems-empty">
        {emptyLabel}
      </Text>
    );
  }
  return (
    <Stack gap="1" role="list">
      {problems.map((problem) => {
        const { tag, detail: hubDetail } = problemTitleParts(problem);
        // A cut line in the H4 card's words, so every place says it the same way (UX-4-3).
        const detail = problem.overflow
          ? tc("overflowTitle", {
              columns: problem.overflow.columns,
              maxColumns: problem.overflow.maxColumns,
              cut: problem.overflow.columns - problem.overflow.maxColumns,
            })
          : hubDetail;
        const kind = tag ?? t(`kind.${problem.kind}`);
        return (
          <Box role="listitem" key={problem.id}>
            <ProblemItem
              severity={problem.severity}
              layout={layout}
              size={size}
              message={problem.line ? t("problemTitle", { kind, line: problem.line }) : kind}
              detail={detail}
              onJump={problem.line ? () => jumpToTemplateLine(problem.line!) : undefined}
              labels={{ error: t("severityError"), warning: t("severityWarning"), jump: t("jumpToSource") }}
            />
          </Box>
        );
      })}
    </Stack>
  );
}

/** H9b sends: SentLog for shown / held / paused, ProblemItems for what never showed. */
export function IdeSentPanel({ ide, size }: { ide: CreatorIdeState; size?: "default" | "touch" }) {
  const t = useTranslations("creatorIde");
  const tDisplays = useTranslations("displays");
  const editTime = useFormatEditTime();
  const model = useMemo(() => sendLogModel(ide.sends, (iso) => editTime(iso)), [ide.sends, editTime]);
  const items = model.items.map((item) => ({
    ...item,
    message: [
      item.boardName ? t("sentTo", { board: item.boardName }) : null,
      item.count > 1 ? t("sentTimes", { count: item.count }) : null,
    ]
      .filter(Boolean)
      .join(" · "),
  }));
  if (ide.sendsError) {
    return (
      <Text size="sm" tone="muted">
        {t("sentUnavailable")}
      </Text>
    );
  }
  return (
    <Stack gap="2">
      {model.notShown.map((send) => (
        <ProblemItem
          key={send.id}
          severity="warning"
          size={size}
          message={send.outcome === "failed" ? t("sendFailed") : t("sendSilenced")}
          detail={[
            editTime(send.at),
            send.board_name ? t("sentTo", { board: send.board_name }) : null,
            send.error ? tDisplays(`fleet.healthErrors.${send.error}`) : null,
          ]
            .filter(Boolean)
            .join(" · ")}
          labels={{ error: t("severityError"), warning: t("severityWarning"), jump: t("jumpToSource") }}
        />
      ))}
      <SentLog
        items={items}
        labels={{
          heading: t("sentHeading"),
          empty: t("sentEmpty"),
          shown: t("sentShown"),
          held: t("sentHeld"),
          paused: t("sentPaused"),
        }}
      />
    </Stack>
  );
}

/**
 * The docked console (04d 4.3, >= 1024 px): Problems | Warnings | Sent under
 * the editor, with the latest send summarized beneath Problems as drawn.
 */
export function IdeConsole({
  ide,
  tab,
  onTabChange,
  quiet = false,
  onOpen,
  onCollapse,
}: {
  ide: CreatorIdeState;
  tab: ConsoleTab;
  onTabChange: (tab: ConsoleTab) => void;
  /** M1: nothing is wrong, so the console is one line ("No problems · Sent 4:57 PM to Kitchen") until opened. */
  quiet?: boolean;
  onOpen?: () => void;
  /** Folds an opened, problem-free console back to its one line (M1). */
  onCollapse?: () => void;
}) {
  const t = useTranslations("creatorIde");
  const tq = useTranslations("ideQuiet");
  const editTime = useFormatEditTime();
  const latest = ide.sends.find((send) => send.outcome === "sent");
  if (quiet) {
    const line = [
      tq("consoleClear"),
      ide.warnings.length ? tq("consoleWarnings", { count: ide.warnings.length }) : null,
      latest
        ? tq("consoleSent", {
            time: editTime(latest.last_at ?? latest.at),
            board: latest.board_name ?? t("aDisplay"),
          })
        : null,
    ]
      .filter(Boolean)
      .join(" · ");
    return (
      <Box as="section" aria-label={t("console")} data-slot="ide-console" data-quiet="" id="ide-console">
        <Button
          variant="ghost"
          aria-expanded={false}
          data-slot="ide-console-line"
          onClick={onOpen}
          // The card is 40 px with its 1 px borders (M1).
          className="h-[38px] w-full justify-between gap-2 rounded-[inherit] px-3.5 text-sm font-normal text-muted-foreground"
        >
          <Text as="span" size="sm" tone="muted" className="truncate">
            {line}
          </Text>
          <ChevronDown aria-hidden="true" className="size-4 shrink-0" />
        </Button>
      </Box>
    );
  }
  const substitutions = substitutionSummary(ide.warnings);
  const sentLine = latest
    ? [
        t("sentSummary", {
          time: editTime(latest.last_at ?? latest.at),
          board: latest.board_name ?? t("aDisplay"),
        }),
        substitutions.length
          ? t("substitutions", { count: substitutions.length, list: substitutions.join(", ") })
          : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : null;
  return (
    <Box as="section" aria-label={t("console")} data-slot="ide-console" id="ide-console">
      <Tabs value={tab} onValueChange={(value) => onTabChange(value as ConsoleTab)}>
        <Flex align="center" gap="1">
          <TabsList className="w-full">
            {/* Three equal tabs across the list (Figma 184:159319, BB-FP-18). */}
            <TabsTrigger value="problems" className="flex-1">
              {t("problemsCount", { count: ide.problems.length })}
            </TabsTrigger>
            <TabsTrigger value="warnings" className="flex-1">
              {t("warningsCount", { count: ide.warnings.length })}
            </TabsTrigger>
            <TabsTrigger value="sent" className="flex-1">
              {t("sentTab")}
            </TabsTrigger>
          </TabsList>
          {onCollapse && (
            <Button
              variant="ghost"
              size="icon"
              aria-label={tq("collapseConsole")}
              aria-expanded={true}
              data-slot="ide-console-collapse"
              onClick={onCollapse}
            >
              <ChevronUp aria-hidden="true" className="size-4" />
            </Button>
          )}
        </Flex>
        <TabsContent value="problems" className="pt-2">
          <Stack gap="2">
            <IdeProblemList problems={ide.problems} emptyLabel={t("noProblems")} layout="inline" />
            {sentLine && (
              <Text size="sm" tone="muted" data-slot="ide-sent-summary">
                {sentLine}
              </Text>
            )}
          </Stack>
        </TabsContent>
        <TabsContent value="warnings" className="pt-2">
          <IdeProblemList problems={ide.warnings} emptyLabel={t("noWarnings")} layout="inline" />
        </TabsContent>
        <TabsContent value="sent" className="pt-2">
          <IdeSentPanel ide={ide} />
        </TabsContent>
      </Tabs>
    </Box>
  );
}
