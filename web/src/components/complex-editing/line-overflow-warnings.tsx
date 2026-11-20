"use client";

import { EditorWarning, EditorWarningAction, Stack, Text } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import type { LineOverflow } from "@/lib/complex-editing";

/**
 * H4 overflow (07c `307:41698` desktop, `307:44268` phone): ONE EditorWarning
 * card for the lines the hub measured past the board's real width. The card
 * names the first line in full; any further lines are listed in it with
 * their Wrap fixes, so one overflow is never a stack of tall cards (BB-E-10).
 */
export function LineOverflowWarnings({
  overflows,
  boardName,
  checkedAt,
  touch,
  wrapped,
  onWrap,
}: {
  overflows: readonly LineOverflow[];
  boardName?: string | null;
  checkedAt: Date | null;
  touch: boolean;
  /** Lines already wrapping (the hub never reports them, but a stale result might). */
  wrapped: readonly boolean[];
  onWrap: (line: number) => void;
}) {
  const t = useTranslations("complexEditing");
  const [first, ...more] = overflows;
  if (!first) return null;
  const time = checkedAt?.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const wrappable = overflows.filter((overflow) => !wrapped[overflow.line - 1]);
  return (
    <Stack gap="2" data-slot="line-overflow-warnings">
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
          wrappable.map((overflow) => (
            <EditorWarningAction key={overflow.line} onClick={() => onWrap(overflow.line)}>
              {t("overflowWrap", { line: overflow.line })}
            </EditorWarningAction>
          ))
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
    </Stack>
  );
}
