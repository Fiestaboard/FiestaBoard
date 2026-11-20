// BB-FP-14 (Figma 306:38107): the Formula sheet's live result, under the
// expression: "→ NICE" and "weather.temp is 72 now · 4 of 22 columns". It
// renders the formula alone on the page's board and preview data (H5 value,
// H7 trace for the variable it read), never on the live route.

"use client";

import { Badge, Flex, Text } from "@fiestaboard/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { useTranslations } from "@/i18n/translations";
import { formulaDebugApi } from "@/lib/api/formula-debug";
import { errorTag } from "@/lib/formula-ide/hints";

import { useFormulaIdeBridge } from "./formula-ide-context";

export interface FormulaResultProps {
  /** The last expression that validated; null while there is none. */
  expression: string | null;
}

export function FormulaResult({ expression }: FormulaResultProps) {
  const t = useTranslations("formulaEditor");
  const preview = useFormulaIdeBridge()?.preview ?? null;
  const enabled = preview !== null && !!expression;
  const { data } = useQuery({
    queryKey: ["formula-ide", "sheet-result", preview?.target, preview?.context, expression],
    queryFn: ({ signal }) =>
      formulaDebugApi.render(
        {
          target: { ...preview!.target, template: [`{{= ${expression} }}`] },
          preview: preview!.context,
          debug: { trace: { line: 1, start: 0 } },
        },
        signal,
      ),
    enabled,
    placeholderData: keepPreviousData,
    retry: false,
  });
  if (!enabled || !data) return null;
  const formula = data.diagnostics?.formulas[0];
  if (!formula) return null;

  const tag = errorTag(formula);
  const value = (formula.value.split("\n")[0] ?? "").trim();
  const variable = data.debug?.trace?.events.find((event) => event.kind === "variable" && !event.error);
  const context = [
    variable ? t("resultVariableNow", { name: variable.label, value: variable.value }) : null,
    tag ? null : t("resultColumns", { used: [...value].length, cols: preview.boardCols }),
  ].filter(Boolean);

  return (
    <Flex align="center" gap="2" wrap data-testid="formula-result" aria-live="polite">
      <Badge variant={tag ? "destructive" : "formula"} className="rounded-full font-mono font-medium">
        {tag ?? t("resultValue", { value: value || '""' })}
      </Badge>
      {context.length > 0 && (
        <Text size="xs" tone="muted">
          {context.join(" · ")}
        </Text>
      )}
    </Flex>
  );
}
