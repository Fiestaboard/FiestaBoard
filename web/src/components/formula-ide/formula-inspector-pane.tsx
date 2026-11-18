// Inspector pane (04c 132:20145): click a cell → its source, the formula's
// executed steps (H7 trace via TraceStep) beside its value, clip report and width.

"use client";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Box,
  Button,
  Card,
  CardContent,
  Flex,
  Skeleton,
  Stack,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Text,
  TraceStep,
  TruncationMap,
} from "@fiestaboard/ui";
import { ChevronLeft, ChevronRight, X } from "lucide-react";

import { useTranslations } from "@/i18n/translations";
import { limitForeach } from "@/lib/formula-ide/fixes";
import { findLine } from "@/lib/formula-ide/hints";
import { iterationCount } from "@/lib/formula-ide/pretty";
import { traceSteps } from "@/lib/formula-ide/trace-steps";

import { clipSummaryKey } from "./line-produces-card";
import type { WorkbenchProps } from "./workbench-types";

export function FormulaInspectorPane(props: WorkbenchProps) {
  const { focus, setFocus, formula, cell, diagnostics, rendered, traceLoading, traceFailed, iteration } = props;
  // A kept previous trace belongs to another formula until the new one lands.
  const trace =
    props.trace && formula && props.trace.line === formula.line && props.trace.start === formula.start
      ? props.trace
      : null;
  const t = useTranslations("formulaIde");
  const stepLabels = { ok: t("stepOk"), error: t("stepError"), skipped: t("stepSkipped") };

  const close = () => setFocus(null);

  if (props.renderFailed) {
    return (
      <Alert variant="destructive" data-testid="inspector-render-failed">
        <AlertDescription>{t("previewFailed")}</AlertDescription>
      </Alert>
    );
  }
  if (props.sourceMapStatus === "limit") {
    return (
      <Alert variant="warning" data-testid="inspector-limit">
        <AlertDescription>{t("sourceMapLimit")}</AlertDescription>
      </Alert>
    );
  }
  if (focus === null) {
    return (
      <Card data-testid="inspector-pane" className="py-4">
        <CardContent className="px-4">
          <Text size="sm" tone="muted">
            {t("inspectHint")}
          </Text>
        </CardContent>
      </Card>
    );
  }

  const row = focus.kind === "cell" ? focus.row + 1 : null;
  const source = cell?.origin?.source;
  if (focus.kind === "cell" && cell && !cell.origin) {
    return (
      <Card data-testid="inspector-pane" className="py-4">
        <CardContent className="px-4">
          <Text size="sm">{t("cellPadding", { row: row ?? 0, col: focus.col + 1 })}</Text>
        </CardContent>
      </Card>
    );
  }

  const lineNumber = formula?.line ?? source?.line ?? null;
  const line = lineNumber != null ? findLine(diagnostics, lineNumber) : undefined;
  const total = trace ? iterationCount(trace.events) : 1;
  const isLoop = total > 1;
  const heading =
    row != null && lineNumber != null
      ? isLoop
        ? t("inspectorHeadingLoop", { row, line: lineNumber, item: iteration + 1, total })
        : t("inspectorHeading", { row, line: lineNumber })
      : t("inspectorHeadingFormula", { line: lineNumber ?? "?" });

  const steps = trace ? traceSteps(trace, iteration) : [];
  const limited =
    formula && line && line.clip && line.rows_shown > 0 ? limitForeach(formula.source, line.rows_shown) : null;
  const clipKey = line ? clipSummaryKey(line) : null;
  const boardRow = row != null ? (rendered[row - 1] ?? "").trimEnd() : null;

  const stepIteration = (delta: number) => {
    if (focus.kind === "formula")
      setFocus({ ...focus, iteration: Math.min(Math.max(iteration + delta, 0), total - 1) });
  };

  const stepsBody =
    formula === undefined ? (
      <Text size="sm" tone="muted">
        {source ? t(`sourceKind_${source.kind}`, { line: source.line }) : t("noFormulaHere")}
      </Text>
    ) : traceLoading && !trace ? (
      <Stack gap="2">
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-4/5" />
        <Skeleton className="h-6 w-3/5" />
      </Stack>
    ) : traceFailed ? (
      <Alert variant="destructive">
        <AlertDescription>{t("traceFailed")}</AlertDescription>
      </Alert>
    ) : (
      <Stack gap="0" role="list" aria-label={t("stepsLabel")} data-testid="trace-steps">
        {steps.map((step) => (
          <Box role="listitem" key={step.id}>
            <TraceStep
              expression={step.expression}
              value={step.value}
              state={step.state}
              depth={step.depth}
              labels={stepLabels}
            />
          </Box>
        ))}
        {trace?.truncated && (
          <Text size="xs" tone="muted">
            {t("traceTruncated")}
          </Text>
        )}
      </Stack>
    );

  return (
    <Card data-testid="inspector-pane" className="gap-3 border-ring py-4">
      <CardContent className="px-4">
        <Tabs defaultValue="steps">
          <Flex align="center" justify="between" gap="2" wrap className="mb-3">
            <Text as="p" weight="semibold" data-testid="inspector-heading">
              {heading}
            </Text>
            <Flex align="center" gap="2">
              <TabsList>
                <TabsTrigger value="value">{t("tabValue")}</TabsTrigger>
                <TabsTrigger value="steps">{t("tabSteps")}</TabsTrigger>
                <TabsTrigger value="width">{t("tabWidth")}</TabsTrigger>
              </TabsList>
              <Button variant="ghost" size="icon-sm" aria-label={t("closeInspector")} onClick={close}>
                <X aria-hidden />
              </Button>
            </Flex>
          </Flex>
          <Box className="grid gap-4 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <Box className="min-w-0">
              <TabsContent value="steps">
                {focus.kind === "formula" && isLoop && (
                  <Flex align="center" gap="1" className="mb-2">
                    <Text size="xs" tone="muted" className="font-mono">
                      {t("valuesForItem")}
                    </Text>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      aria-label={t("previousItem")}
                      onClick={() => stepIteration(-1)}
                    >
                      <ChevronLeft aria-hidden />
                    </Button>
                    <Text size="xs" className="font-mono">
                      {t("itemOf", { item: iteration + 1, total })}
                    </Text>
                    <Button variant="ghost" size="icon-xs" aria-label={t("nextItem")} onClick={() => stepIteration(1)}>
                      <ChevronRight aria-hidden />
                    </Button>
                  </Flex>
                )}
                {stepsBody}
              </TabsContent>
              <TabsContent value="value">
                <Text size="sm" className="font-mono whitespace-pre-wrap" data-testid="inspector-value">
                  {formula ? (formula.error ?? formula.value) : (boardRow ?? "")}
                </Text>
              </TabsContent>
              <TabsContent value="width">
                {line ? (
                  <TruncationMap
                    columns={props.boardCols}
                    title={t("widthTitle", { line: line.line })}
                    lines={[{ row: line.first_row ?? 1, length: line.widest }]}
                  />
                ) : (
                  <Text size="sm" tone="muted">
                    {t("noLineReport")}
                  </Text>
                )}
              </TabsContent>
            </Box>
            <Stack gap="3" className="min-w-0">
              {boardRow !== null && (
                <Box className="rounded-lg bg-muted px-3 py-2">
                  <Text size="sm">
                    {t("rowShows", { row: row ?? 0 })}{" "}
                    <Text as="span" size="sm" weight="semibold" className="font-mono whitespace-pre">
                      {boardRow || " "}
                    </Text>
                  </Text>
                </Box>
              )}
              {line && line.clip && (
                <Alert variant="warning" data-testid="clip-report">
                  <AlertTitle>{t("rowsShownSummary", { shown: line.rows_shown, wanted: line.rows_wanted })}</AlertTitle>
                  <AlertDescription>
                    <Stack gap="2">
                      {clipKey && <Text size="sm">{t(clipKey, { line: line.clip_line ?? "" })}</Text>}
                      {line.hidden.length > 0 && (
                        <Text size="xs" className="font-mono">
                          {t("hiddenRows", { rows: line.hidden.map((r) => r.trim()).join(" · ") })}
                        </Text>
                      )}
                      {limited && formula && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="self-start"
                          onClick={() => props.onReplaceFormula(formula.line, formula.source.trim(), limited)}
                        >
                          {t("limitTo", { rows: line.rows_shown })}
                        </Button>
                      )}
                    </Stack>
                  </AlertDescription>
                </Alert>
              )}
              {line && (
                <Text size="xs" tone="muted" className="font-mono">
                  {t("widestRow", { widest: line.widest, cols: props.boardCols })}
                  {line.cut ? ` · ${t("rowCut")}` : ""}
                </Text>
              )}
            </Stack>
          </Box>
        </Tabs>
      </CardContent>
    </Card>
  );
}
