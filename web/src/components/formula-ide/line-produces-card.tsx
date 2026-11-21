// "Line N produces" (04c 111:30911 / 132:20145): what one template line put on
// the board, row by row, and what was clipped (H5 line report).

"use client";

import { Card, CardContent, CardHeader, CardTitle, Stack, Text } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import type { LineDiagnostic } from "@/lib/api/formula-debug";

export function clipSummaryKey(line: LineDiagnostic): string | null {
  switch (line.clip) {
    case "stopped_by_line":
      return "clipStoppedByLine";
    case "board_end":
      return "clipBoardEnd";
    case "covered":
      return "clipCovered";
    case "beyond_board":
      return "clipBeyondBoard";
    default:
      return null;
  }
}

export function LineProducesCard({ line, rendered }: { line: LineDiagnostic; rendered: readonly string[] }) {
  const t = useTranslations("formulaIde");
  const shown =
    line.first_row != null
      ? Array.from({ length: line.rows_shown }, (_, i) => ({
          row: line.first_row! + i,
          text: rendered[line.first_row! - 1 + i] ?? "",
        }))
      : [];
  const hiddenFrom = line.first_row != null ? line.first_row + line.rows_shown : null;
  const clipKey = clipSummaryKey(line);
  return (
    <Card data-testid="line-produces" className="gap-2 py-4">
      <CardHeader className="px-4">
        {/* Heading/sm 14/600 (Figma 111:30911). */}
        <CardTitle as="h3" className="text-sm">
          {t("lineProduces", { line: line.line })}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4">
        <Stack gap="1">
          {shown.map(({ row, text }) => (
            <Text key={row} size="sm" className="grid grid-cols-[5rem_1fr] font-mono whitespace-pre">
              <Text as="span" size="sm" tone="muted" className="font-mono">
                {t("rowLabel", { row })}
              </Text>
              {text.trimEnd() || " "}
            </Text>
          ))}
          {line.hidden.length > 0 && hiddenFrom != null && (
            <Text size="sm" tone="warning" className="grid grid-cols-[5rem_1fr] font-mono whitespace-pre-wrap">
              <Text as="span" size="sm" tone="muted" className="font-mono">
                {t("rowsLabel", { from: hiddenFrom, to: hiddenFrom + line.hidden.length - 1 })}
              </Text>
              {line.hidden.map((row) => row.trim()).join(" · ")}
            </Text>
          )}
          {line.first_row == null && (
            <Text size="sm" tone="muted">
              {t("lineShowsNowhere")}
            </Text>
          )}
          <Text size="xs" tone={line.clip ? "warning" : "muted"}>
            {t("rowsShownSummary", { shown: line.rows_shown, wanted: line.rows_wanted })}
            {clipKey && ` · ${t(clipKey, { line: line.clip_line ?? "" })}`}
          </Text>
        </Stack>
      </CardContent>
    </Card>
  );
}
