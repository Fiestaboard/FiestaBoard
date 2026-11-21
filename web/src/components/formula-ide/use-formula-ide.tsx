// Web 2.10 (04c): the page editor's formula IDE state, mounted by PageBuilder
// through a handful of additive seams. Everything here reads real hub data:
// H5 per-formula values, H6 preview context, H7 trace and cell source map,
// all on `POST /templates/render` (never the live route).

"use client";

import type { DataSource, StatusDotProps } from "@fiestaboard/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { lazy, type ReactNode, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import {
  formulaDebugApi,
  type FormulaDebugRenderResponse,
  type RenderDiagnostics,
  type RenderTarget,
} from "@/lib/api/formula-debug";
import { atIsoForTime, buildPreviewContext, referencedRoots, sampleValues } from "@/lib/formula-ide/data-source";
import {
  buildHintIndex,
  buildVariableHintIndex,
  findFormula,
  normalizeSource,
  templateVariablePaths,
  variableProbeTemplate,
} from "@/lib/formula-ide/hints";
import { cellOrigin, originDetail } from "@/lib/formula-ide/source-map";

import { BoardCellHighlight } from "./board-cell-highlight";
import type { FormulaIdeBridge, FormulaPreviewTarget, OpenFormulaRequest } from "./formula-ide-context";
import { MissingValuesCard } from "./missing-values-card";
import { PreviewDataControls } from "./preview-data-controls";
import type { WorkbenchProps } from "./workbench-types";

const FormulaWorkbenchLeft = lazy(() =>
  import("./formula-workbench").then((m) => ({ default: m.FormulaWorkbenchLeft })),
);
const FormulaWorkbenchRight = lazy(() =>
  import("./formula-workbench").then((m) => ({ default: m.FormulaWorkbenchRight })),
);
const InspectSheet = lazy(() => import("./inspect-sheet").then((m) => ({ default: m.InspectSheet })));

export type WorkbenchTab = "code" | "builder";

export interface OpenFormulaState extends OpenFormulaRequest {
  /** Bumped per open so the editor remounts on a different chip. */
  key: number;
  tab: WorkbenchTab;
  /** The edited body, shared by Code and Builder; null until edited. */
  draft: string | null;
}

/** What the inspector and the "Line N produces" card are about. */
export type InspectFocus =
  { kind: "cell"; row: number; col: number } | { kind: "formula"; expression: string; iteration: number };

export interface UseFormulaIdeOptions {
  /** The board and template the preview renders; null keeps the IDE inert (canvases, plain text boards). */
  target: RenderTarget | null;
  /**
   * Whether this editor offers the IDE at all (not canvases or a plain-text
   * board). The preview controls follow this, not `target`, so they are there
   * from the first render instead of appearing when the debounced template
   * lands (which would grow the docked preview under open menus). Defaults to
   * `target !== null`.
   */
  available?: boolean;
  /**
   * The editor's own preview render, with its H5 diagnostics. When given, Live
   * at the real time reads from it and the IDE renders through the hub only
   * for Sample, Missing, another time or Inspect, so an edit costs one render,
   * not two.
   */
  live?: { diagnostics: RenderDiagnostics | null; lines: string[]; failed?: boolean };
  /** ≥1024 px: docked workbench, inspector and header controls. */
  desktop: boolean;
  mirroring: boolean;
  stopMirroring: () => void;
  /** Board width in tiles (fit reports). */
  boardCols: number;
  /** Rewrites one template line (one-tap fixes). */
  editTemplateLine: (index: number, edit: (line: string) => string) => void;
}

export interface FormulaIde {
  bridge: FormulaIdeBridge;
  /** The board text to show instead of the ordinary preview (Sample, Missing, or another time). */
  previewOverride: string | null;
  dotStatus?: StatusDotProps["status"];
  /** Mirror-to-board is off while the preview is not live data at the real time. */
  mirrorLocked: boolean;
  /** The render behind the hints failed: the IDE's own, or the editor's preview in Live. */
  renderFailed: boolean;
  headerControls: ReactNode;
  bodyControls: ReactNode;
  previewFooter: ReactNode;
  boardProps: {
    ref: React.RefObject<HTMLDivElement | null>;
    onClick?: (event: React.MouseEvent<HTMLDivElement>) => void;
    className?: string;
    "data-inspecting"?: boolean;
  };
  boardOverlay: ReactNode;
  leftSlot: ReactNode;
  rightSlot: ReactNode;
  overlays: ReactNode;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || !!target.closest(".cm-editor");
}

export function useFormulaIde({
  target,
  live,
  available = target !== null,
  desktop,
  mirroring,
  stopMirroring,
  boardCols,
  editTemplateLine,
}: UseFormulaIdeOptions): FormulaIde {
  const t = useTranslations("formulaIde");
  const [chosenMode, setModeState] = useState<DataSource>("live");
  const [chosenAt, setAtTime] = useState("");
  // Mirroring shows what the board shows now: live data at the real time.
  const mode: DataSource = mirroring ? "live" : chosenMode;
  const atTime = mirroring ? "" : chosenAt;
  const [inspect, setInspect] = useState(false);
  const [focus, setFocus] = useState<InspectFocus | null>(null);
  const [open, setOpen] = useState<OpenFormulaState | null>(null);
  const [sheetExpression, setSheetExpression] = useState<string | null>(null);
  const openCounter = useRef(0);
  const boardRef = useRef<HTMLDivElement | null>(null);

  const { data: variables } = useQuery({
    queryKey: ["template-variables"],
    queryFn: api.getTemplateVariables,
    staleTime: 5 * 60 * 1000,
  });

  const template = useMemo(() => target?.template ?? [], [target]);
  const roots = useMemo(
    () => referencedRoots(template, Object.keys(variables?.variables ?? {})),
    [template, variables],
  );
  const sample = useMemo(
    () => sampleValues(variables?.variable_metadata as Parameters<typeof sampleValues>[0], roots),
    [variables, roots],
  );
  const atIso = atTime ? atIsoForTime(atTime, new Date()) : null;
  const previewContext = useMemo(
    () => buildPreviewContext({ mode, roots, sample: sample.values, at: atIso }),
    [mode, roots, sample.values, atIso],
  );
  const wantSourceMap = desktop && inspect;

  // Without the editor's own render (`live`) the IDE renders Live itself.
  const ownRender = target !== null && (previewContext !== null || wantSourceMap || live === undefined);
  const render = useQuery<FormulaDebugRenderResponse>({
    queryKey: ["formula-ide", "render", target, previewContext, wantSourceMap],
    queryFn: ({ signal }) =>
      formulaDebugApi.render(
        { target: target!, preview: previewContext, debug: wantSourceMap ? { sourceMap: true } : null },
        signal,
      ),
    enabled: ownRender,
    placeholderData: keepPreviousData,
    retry: false,
  });
  // A kept previous result belongs to another context once the IDE stops rendering itself.
  const own = ownRender ? render.data : undefined;
  // In Sample/Missing/another time the Live values would mislead; elsewhere they fill the gap while loading.
  const diagnostics =
    previewContext !== null ? (own?.diagnostics ?? null) : (own?.diagnostics ?? live?.diagnostics ?? null);
  const sourceMap = own?.debug?.source_map ?? null;

  const missingRoots = useMemo(() => (mode === "missing" ? roots : []), [mode, roots]);
  const hints = useMemo(() => buildHintIndex(diagnostics, missingRoots), [diagnostics, missingRoots]);

  // BB-FP-11: variable chips show their value too. One probe render evaluates
  // every variable path as a formula, for the same board and preview context.
  const variablePaths = useMemo(() => templateVariablePaths(template), [template]);
  const probeTarget = useMemo<RenderTarget | null>(
    () =>
      target === null || variablePaths.length === 0
        ? null
        : {
            template: variableProbeTemplate(variablePaths),
            deviceType: target.deviceType,
            notesWide: target.notesWide,
            notesTall: target.notesTall,
            grid: target.grid,
            boardId: target.boardId,
          },
    [target, variablePaths],
  );
  const formulaPreview = useMemo<FormulaPreviewTarget | null>(
    () =>
      target === null
        ? null
        : {
            target: {
              deviceType: target.deviceType,
              notesWide: target.notesWide,
              notesTall: target.notesTall,
              grid: target.grid,
              boardId: target.boardId,
            },
            context: previewContext,
            boardCols,
          },
    [target, previewContext, boardCols],
  );
  const variableRender = useQuery<FormulaDebugRenderResponse>({
    queryKey: ["formula-ide", "variables", probeTarget, previewContext],
    queryFn: ({ signal }) => formulaDebugApi.render({ target: probeTarget!, preview: previewContext }, signal),
    enabled: probeTarget !== null,
    placeholderData: keepPreviousData,
    // Keyed on the variable set, not the text, so an edit doesn't re-probe;
    // live data is re-read on the preview's own cadence instead.
    staleTime: 30_000,
    refetchInterval: 30_000,
    retry: false,
  });
  const variableHints = useMemo(
    () => buildVariableHintIndex(probeTarget ? variableRender.data?.diagnostics : null),
    [probeTarget, variableRender.data],
  );

  // The formula the inspector, the trace and the line card are about.
  const cellDetail = useMemo(() => {
    if (focus?.kind !== "cell" || !sourceMap) return null;
    const origin = cellOrigin(sourceMap, focus.row, focus.col);
    if (!origin) return { origin: null, detail: null };
    return { origin, detail: originDetail(origin.source, diagnostics, focus.row) };
  }, [focus, sourceMap, diagnostics]);

  const focusFormula = useMemo(() => {
    if (focus?.kind === "formula") return findFormula(diagnostics, focus.expression);
    if (focus?.kind === "cell") return cellDetail?.detail?.formula;
    if (open) return findFormula(diagnostics, open.expression);
    return undefined;
  }, [focus, cellDetail, open, diagnostics]);
  const sheetFormula = sheetExpression !== null ? findFormula(diagnostics, sheetExpression) : undefined;
  const traceFormula = sheetFormula ?? focusFormula;
  const iteration =
    focus?.kind === "formula"
      ? focus.iteration
      : focus?.kind === "cell"
        ? Math.max((cellDetail?.detail?.rowInFormula ?? 1) - 1, 0)
        : 0;

  const traceSelection = traceFormula ? { line: traceFormula.line, start: traceFormula.start } : null;
  const trace = useQuery({
    queryKey: ["formula-ide", "trace", target, previewContext, traceSelection],
    queryFn: ({ signal }) =>
      formulaDebugApi.render({ target: target!, preview: previewContext, debug: { trace: traceSelection } }, signal),
    enabled: target !== null && traceSelection !== null,
    placeholderData: keepPreviousData,
    retry: false,
    select: (data) => data.debug?.trace ?? null,
  });

  const setMode = useCallback(
    (next: DataSource) => {
      if (next !== "live" && mirroring) stopMirroring();
      setModeState(next);
    },
    [mirroring, stopMirroring],
  );
  const setAt = useCallback(
    (value: string) => {
      if (value && mirroring) stopMirroring();
      setAtTime(value);
    },
    [mirroring, stopMirroring],
  );

  // `I` toggles Inspect on desktop, outside text inputs (04c C3).
  useEffect(() => {
    if (!desktop || target === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "i" || event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      event.preventDefault();
      setInspect((value) => !value);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [desktop, target]);

  // The template line the docked editor or Inspect is about (BB-FP-15/16): a
  // primitive, so a keystroke in the editor (a new `open` draft) doesn't give
  // the bridge, and every chip, a new identity. A plain-text cell falls back
  // to its source line.
  const activeLine = activeTemplateLine({
    desktop,
    editing: open !== null,
    inspecting: inspect && focus !== null,
    formulaLine: focusFormula?.line,
    cellLine: cellDetail?.origin?.source.line,
  });

  const bridge = useMemo<FormulaIdeBridge>(
    () => ({
      hint: (expression) => hints.get(normalizeSource(expression)),
      variableHint: (path) => variableHints.get(path),
      preview: formulaPreview,
      activeLine,
      openFormula: (request) => {
        if (!desktop || target === null) return false;
        openCounter.current += 1;
        setOpen({ ...request, key: openCounter.current, tab: "code", draft: null });
        setFocus(null);
        return true;
      },
      inspectFormula: (expression) => {
        if (desktop && target !== null) {
          setInspect(true);
          setFocus({ kind: "formula", expression, iteration: 0 });
        } else {
          setSheetExpression(expression);
        }
      },
    }),
    [hints, variableHints, formulaPreview, desktop, target, activeLine],
  );

  const inert = target === null;
  const previewOverride = !inert && previewContext !== null ? (own?.rendered ?? null) : null;
  const atLabel = atTime ? formatClock(atTime) : null;

  const controls = (size: "default" | "touch") =>
    !available ? null : (
      <PreviewDataControls
        mode={mode}
        onModeChange={setMode}
        atTime={atTime}
        onAtTimeChange={setAt}
        size={size}
        inspect={desktop ? inspect : undefined}
        onInspectChange={desktop ? setInspect : undefined}
      />
    );

  const footer = inert ? null : (
    <MissingValuesCard
      mode={mode}
      atLabel={atLabel}
      template={template}
      roots={roots}
      unsampled={sample.unsampled}
      formulas={diagnostics?.formulas ?? []}
      sources={own?.sources ?? null}
      loading={render.isPending && previewContext !== null}
      failed={render.isError && previewContext !== null}
      onAddFallback={(line, path) =>
        editTemplateLine(line - 1, (text) => text.replace(`{{${path}}}`, `{{= DEFAULT(${path}, "--") }}`))
      }
    />
  );

  const highlightRows = useMemo(() => {
    if (!sourceMap || !cellDetail?.origin) return [];
    const index = cellDetail.origin.index;
    const cells: Array<[number, number]> = [];
    sourceMap.cells.forEach((row, r) => row.forEach((value, c) => value === index && cells.push([r, c])));
    return cells;
  }, [sourceMap, cellDetail]);

  const onBoardClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const tile = (event.target as HTMLElement).closest<HTMLElement>("[data-row][data-col]");
    if (!tile || !boardRef.current?.contains(tile)) return;
    setFocus({ kind: "cell", row: Number(tile.dataset.row), col: Number(tile.dataset.col) });
  };

  const showWorkbench = desktop && !inert && (open !== null || inspect);
  // A failed render means no hints: the IDE's own in Sample/Missing/at/Inspect;
  // the editor's preview in Live. While mirroring the live render is the one
  // behind the hints, so a stale preview error does not count (FABLE-2541 N15).
  const renderFailed = ownRender ? render.isError : !mirroring && (live?.failed ?? false);
  const workbenchProps = {
    open,
    setOpen,
    focus,
    setFocus,
    inspect,
    iteration,
    formula: focusFormula,
    cell: cellDetail,
    diagnostics,
    rendered: own?.lines ?? live?.lines ?? [],
    trace: trace.data ?? null,
    traceLoading: trace.isFetching,
    traceFailed: trace.isError,
    sourceMapStatus: own?.debug?.source_map_status ?? null,
    // A failed render means no hints: the IDE's own in Sample/Missing/at/Inspect,
    // the editor's preview render in Live (N13).
    renderFailed,
    boardCols,
    onReplaceFormula: (line: number, from: string, to: string) =>
      editTemplateLine(line - 1, (text) => text.replace(from, to)),
  } satisfies WorkbenchProps;

  return {
    bridge,
    previewOverride,
    dotStatus: !inert && mode === "sample" ? "neutral" : undefined,
    mirrorLocked: !inert && previewContext !== null,
    renderFailed,
    headerControls: desktop ? controls("default") : null,
    bodyControls: desktop ? null : controls("touch"),
    previewFooter: footer,
    boardProps: {
      ref: boardRef,
      ...(desktop && inspect && !inert
        ? { onClick: onBoardClick, className: "relative cursor-crosshair", "data-inspecting": true }
        : { className: "relative" }),
    },
    boardOverlay:
      desktop && inspect && focus?.kind === "cell" ? (
        <BoardCellHighlight containerRef={boardRef} cells={highlightRows} selected={[focus.row, focus.col]} />
      ) : null,
    leftSlot: showWorkbench ? (
      <Suspense fallback={null}>
        <FormulaWorkbenchLeft {...workbenchProps} />
      </Suspense>
    ) : null,
    rightSlot: showWorkbench ? (
      <Suspense fallback={null}>
        <FormulaWorkbenchRight {...workbenchProps} />
      </Suspense>
    ) : null,
    overlays:
      sheetExpression !== null ? (
        <Suspense fallback={null}>
          <InspectSheet
            expression={sheetExpression}
            formula={sheetFormula}
            diagnostics={diagnostics}
            trace={trace.data ?? null}
            loading={(ownRender && render.isPending) || trace.isFetching}
            failed={trace.isError}
            mode={mode}
            atLabel={atLabel}
            boardCols={boardCols}
            onClose={() => setSheetExpression(null)}
          />
        </Suspense>
      ) : null,
  };
}

/**
 * The template line to tint (BB-FP-15/16): the formula being edited or
 * inspected, else an inspected plain-text cell's source line. Desktop only.
 */
export function activeTemplateLine({
  desktop,
  editing,
  inspecting,
  formulaLine,
  cellLine,
}: {
  desktop: boolean;
  editing: boolean;
  inspecting: boolean;
  formulaLine?: number;
  cellLine?: number;
}): number | null {
  if (!desktop || !(editing || inspecting)) return null;
  return formulaLine ?? cellLine ?? null;
}

/** "07:00" → "7:00 AM" in the viewer's locale. */
export function formatClock(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  const date = new Date(2000, 0, 1, h, m);
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
