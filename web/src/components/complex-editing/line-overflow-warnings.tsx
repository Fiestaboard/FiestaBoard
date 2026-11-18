"use client";

import { EditorWarning, EditorWarningAction, Stack } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import type { LineOverflow } from "@/lib/complex-editing";

/**
 * H4 per-line overflow (07c `307:41698` desktop, `307:44268` phone): one
 * EditorWarning card per line the hub measured past the board's real width.
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
  if (overflows.length === 0) return null;
  const time = checkedAt?.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return (
    <Stack gap="2" data-slot="line-overflow-warnings">
      {overflows.map((overflow) => (
        <EditorWarning
          key={overflow.line}
          kind="line-overflow"
          size={touch ? "touch" : "default"}
          line={overflow.line}
          columns={overflow.columns}
          maxColumns={overflow.maxColumns}
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
            !wrapped[overflow.line - 1] && (
              <EditorWarningAction onClick={() => onWrap(overflow.line)}>
                {t("overflowWrap", { line: overflow.line })}
              </EditorWarningAction>
            )
          }
        >
          {t("overflowBody", { line: overflow.line, maxColumns: overflow.maxColumns, cut: overflow.cut })}
        </EditorWarning>
      ))}
    </Stack>
  );
}
