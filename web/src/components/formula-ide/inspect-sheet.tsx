// Phone Inspect (07c 307:45424): long-press a formula chip › a read-only
// bottom sheet with its source, each step with its value (TraceStep, per the
// 1.11 ruling — no Badge list) and the line's fit report from the hub.

"use client";

import {
  Alert,
  AlertDescription,
  Badge,
  Box,
  type DataSource,
  Flex,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Stack,
  Text,
  TraceStep,
} from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import type { FormulaDiagnostic, FormulaTrace, RenderDiagnostics } from "@/lib/api/formula-debug";
import { findLine } from "@/lib/formula-ide/hints";
import { traceSteps } from "@/lib/formula-ide/trace-steps";

export interface InspectSheetProps {
  expression: string;
  formula: FormulaDiagnostic | undefined;
  diagnostics: RenderDiagnostics | null;
  trace: FormulaTrace | null;
  loading: boolean;
  failed: boolean;
  mode: DataSource;
  atLabel: string | null;
  boardCols: number;
  onClose: () => void;
}

export function InspectSheet({
  expression,
  formula,
  diagnostics,
  trace,
  loading,
  failed,
  mode,
  atLabel,
  boardCols,
  onClose,
}: InspectSheetProps) {
  const t = useTranslations("formulaIde");
  const line = formula ? findLine(diagnostics, formula.line) : undefined;
  const steps =
    trace && formula && trace.line === formula.line && trace.start === formula.start ? traceSteps(trace, 0) : [];
  const clock = atLabel ?? new Date().toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  const modeLabel = { live: t("live"), sample: t("sample"), missing: t("missing") }[mode];
  const fits = line ? !line.cut && line.clip === null : null;

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="bottom" data-testid="inspect-sheet">
        <SheetHeader>
          <SheetTitle>{formula ? t("inspectLine", { line: formula.line }) : t("inspectFormula")}</SheetTitle>
          <SheetDescription className="sr-only">{t("inspectSheetDescription")}</SheetDescription>
        </SheetHeader>
        <Stack gap="3" className="px-4 pb-6">
          <Stack gap="1">
            <Text size="xs" tone="muted" className="font-mono uppercase">
              {t("source")}
            </Text>
            <Text size="sm" className="font-mono break-all">{`{{= ${expression} }}`}</Text>
          </Stack>
          <Stack gap="1">
            <Text size="xs" tone="muted" className="font-mono uppercase">
              {t("stepsAt", { mode: modeLabel, time: clock })}
            </Text>
            {!formula && !loading ? (
              <Text size="sm" tone="muted">
                {t("notRendered")}
              </Text>
            ) : failed ? (
              <Alert variant="destructive">
                <AlertDescription>{t("traceFailed")}</AlertDescription>
              </Alert>
            ) : steps.length === 0 ? (
              <Stack gap="2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-4/5" />
              </Stack>
            ) : (
              <Box
                role="list"
                aria-label={t("stepsLabel")}
                className="rounded-xl border px-2"
                data-testid="trace-steps"
              >
                {steps.map((step) => (
                  <Box role="listitem" key={step.id}>
                    <TraceStep
                      expression={step.expression}
                      value={step.value}
                      state={step.state}
                      labels={{ ok: t("stepOk"), error: t("stepError"), skipped: t("stepSkipped") }}
                    />
                  </Box>
                ))}
              </Box>
            )}
          </Stack>
          {line && (
            <Flex align="center" gap="2" wrap data-testid="fit-report">
              <Badge variant={fits ? "success" : "destructive"}>{fits ? t("fits") : t("doesNotFit")}</Badge>
              <Text size="sm">
                {t("fitReport", { line: line.line, widest: line.widest, cols: boardCols })}
                {" · "}
                {line.cut
                  ? t("rowCut")
                  : line.clip
                    ? t("rowsShownSummary", { shown: line.rows_shown, wanted: line.rows_wanted })
                    : t("nothingCut")}
              </Text>
            </Flex>
          )}
        </Stack>
      </SheetContent>
    </Sheet>
  );
}
