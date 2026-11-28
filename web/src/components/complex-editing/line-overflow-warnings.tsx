"use client";

import { EditorWarning, EditorWarningAction, Stack, Text } from "@fiestaboard/ui";
import { useId } from "react";

import { useTranslations } from "@/i18n/translations";
import { type LineOverflow, type RowsPastBoard, wrapRowsShort } from "@/lib/complex-editing";
import { jumpToTemplateLine } from "@/lib/ide/jump-to-line";

/**
 * H4 overflow (07c `307:41698` desktop, `307:44268` phone): ONE EditorWarning
 * card for the lines the hub measured past the board's real width. The card
 * names the first line in full; any further lines are listed in it with
 * their Wrap fixes, so one overflow is never a stack of tall cards (BB-E-10).
 *
 * W-1: a Wrap the board has no rows for is disabled with the reason, and the
 * rows the board runs out of (`beyond_board`) are a card in the same family,
 * titled as the Problems console titles them.
 */
export function LineOverflowWarnings({
  overflows,
  pastBoard = [],
  lines,
  rows,
  boardName,
  checkedAt,
  touch,
  wrapped,
  onWrap,
}: {
  overflows: readonly LineOverflow[];
  /** Lines the hub says run past the board's last row. */
  pastBoard?: readonly RowsPastBoard[];
  /** The template, to tell whether a Wrap has blank rows below to fill. */
  lines: readonly string[];
  /** The board's rows. */
  rows: number;
  boardName?: string | null;
  checkedAt: Date | null;
  touch: boolean;
  /** Lines already wrapping (the hub never reports them, but a stale result might). */
  wrapped: readonly boolean[];
  onWrap: (line: number) => void;
}) {
  const t = useTranslations("complexEditing");
  const tIde = useTranslations("creatorIde");
  const reasonId = useId();
  const [first, ...more] = overflows;
  const [firstPast, ...morePast] = pastBoard;
  if (!first && !firstPast) return null;
  const time = checkedAt?.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const wrappable = overflows.filter((overflow) => !wrapped[overflow.line - 1]);
  const wrap = (line: number) => {
    onWrap(line);
    // The button goes with the problem it fixed: the caret goes back to the line.
    jumpToTemplateLine(line);
  };
  return (
    <Stack gap="2" data-slot="line-overflow-warnings">
      {first && (
        <EditorWarning
          kind="line-overflow"
          size={touch ? "touch" : "default"}
          line={first.line}
          columns={first.columns}
          maxColumns={first.maxColumns}
          labels={{
            line: (line) => t("overflowLine", { line }),
            lineOverflow: ({ columns, maxColumns, cut }) => t("overflowTitle", { columns, maxColumns, cut }),
          }}
          checked={
            time
              ? boardName
                ? t("overflowChecked", { board: boardName, time })
                : t("overflowCheckedNoBoard", { time })
              : undefined
          }
          actions={
            wrappable.length > 0 &&
            wrappable.map((overflow) => {
              const short = wrapRowsShort(overflow, lines, wrapped, rows);
              const id = `${reasonId}-${overflow.line}`;
              return short > 0 ? (
                <Text as="span" key={overflow.line} className="inline-flex items-center gap-2">
                  <EditorWarningAction disabled aria-describedby={id}>
                    {t("overflowWrap", { line: overflow.line })}
                  </EditorWarningAction>
                  <Text as="span" id={id} size="xs" tone="muted" data-slot="line-overflow-wrap-reason">
                    {t("overflowWrapNeedsRows", { count: short })}
                  </Text>
                </Text>
              ) : (
                <EditorWarningAction key={overflow.line} onClick={() => wrap(overflow.line)}>
                  {t("overflowWrap", { line: overflow.line })}
                </EditorWarningAction>
              );
            })
          }
        >
          {t("overflowBody", { line: first.line, maxColumns: first.maxColumns, cut: first.cut })}
          {more.length > 0 && (
            <Text as="span" size="xs" weight="medium" className="mt-1 block">
              {t("overflowMore", {
                lines: more.map((overflow) => t("overflowLine", { line: overflow.line })).join(", "),
              })}
            </Text>
          )}
        </EditorWarning>
      )}
      {firstPast && (
        <EditorWarning
          kind="line-overflow"
          size={touch ? "touch" : "default"}
          data-problem={firstPast.kind}
          line={firstPast.line}
          columns={rows}
          maxColumns={rows}
          labels={{ line: () => tIde(`kind.${firstPast.kind}`), lineOverflow: () => firstPast.message }}
        >
          {morePast.length > 0 &&
            morePast.map((past) => (
              <Text as="span" key={past.line} size="xs" weight="medium" className="block">
                {past.message}
              </Text>
            ))}
        </EditorWarning>
      )}
    </Stack>
  );
}
