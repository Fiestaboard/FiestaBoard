"use client";

import {
  Box,
  ColumnRuler,
  EditorWarning,
  EditorWarningAction,
  Flex,
  GoToCell,
  type GoToCellPosition,
  NoteFocus,
  RowBand,
  type RowBandMenuItem,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { type RefObject, useEffect, useMemo, useRef, useState } from "react";

import type { ComplexEditing } from "@/components/complex-editing/use-complex-editing";
import { useTranslations } from "@/i18n/translations";
import {
  deriveRowBands,
  duplicateBand,
  type LineOverflow,
  moveBand,
  noteSeamMarks,
  type SeamStraddle,
  type TemplateRowsState,
} from "@/lib/complex-editing";
import { type LineBox, measureLineBoxes } from "@/lib/complex-editing-dom";

const RULER_TICK_INSET = 14;

/**
 * The template pane's header lenses: Go to (big board, 04b `126:149604`) and
 * Note focus with a seam ruler (note array, 04b `127:135751`).
 */
export function ComplexTemplateHeader({
  complex,
  editorRootRef,
  onGo,
}: {
  complex: ComplexEditing;
  /** The template editor's container: the ruler lines up with its text. */
  editorRootRef: RefObject<HTMLElement | null>;
  onGo: (position: GoToCellPosition) => void;
}) {
  const t = useTranslations("complexEditing");
  if (!complex.active) return null;
  return (
    <Stack gap="2" data-slot="complex-template-header">
      {complex.bigBoard && (
        <Flex align="center" justify="between" gap="2" className="flex-wrap">
          <Text size="xs" tone="muted">
            {t("templateMeta", { rows: complex.rows })}
          </Text>
          <GoToCell
            className="w-[210px]"
            columns={complex.cols}
            rows={complex.rows}
            onGo={onGo}
            labels={{
              input: t("goToInput"),
              hint: t("goToHint"),
              format: (row, column) => t("goToFormat", { row, column }),
              invalid: t("goToInvalid"),
              range: (rows, columns) => t("goToRange", { rows, columns }),
            }}
          />
        </Flex>
      )}
      {complex.noteArray && (
        <>
          <NoteFocus
            note={complex.note}
            notesWide={complex.notesWide}
            notesTall={complex.notesTall}
            onNoteChange={(note, range) => {
              complex.setNote(note);
              complex.scrollToColumn(range ? range.columnStart + 1 : 1);
            }}
            labels={{
              group: t("noteFocusGroup"),
              allNotes: t("noteFocusAll"),
              note: (note) => t("noteFocusNote", { note }),
            }}
          />
          <TemplateSeamRuler complex={complex} editorRootRef={editorRootRef} />
        </>
      )}
    </Stack>
  );
}

/** A seam ruler above the template text, at the editor's monospace pitch. */
function TemplateSeamRuler({
  complex,
  editorRootRef,
}: {
  complex: ComplexEditing;
  editorRootRef: RefObject<HTMLElement | null>;
}) {
  const t = useTranslations("complexEditing");
  const probeRef = useRef<HTMLSpanElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [metrics, setMetrics] = useState({ pitch: 0, left: 0 });

  useEffect(() => {
    const measure = () => {
      const probe = probeRef.current;
      const box = boxRef.current;
      const text = editorRootRef.current?.querySelector('[contenteditable="true"] p, textarea');
      if (!probe || !box) return;
      const pitch = probe.getBoundingClientRect().width / 10;
      const left = text ? text.getBoundingClientRect().left - box.getBoundingClientRect().left : 0;
      setMetrics((previous) => (previous.pitch === pitch && previous.left === left ? previous : { pitch, left }));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    if (boxRef.current) observer.observe(boxRef.current);
    return () => observer.disconnect();
  }, [editorRootRef]);

  const marks = useMemo(
    () => noteSeamMarks(complex.notesWide, t("seamMark")).map((mark) => ({ ...mark, gap: 0 })),
    [complex.notesWide, t],
  );
  return (
    <Box ref={boxRef} className="relative overflow-hidden" data-slot="complex-template-ruler">
      <Text as="span" ref={probeRef} aria-hidden="true" className="invisible absolute font-mono text-sm">
        MMMMMMMMMM
      </Text>
      {metrics.pitch > 0 && (
        <ColumnRuler
          columns={complex.cols}
          columnPitch={metrics.pitch}
          marks={marks}
          label={t("seamRulerLabel", { columns: complex.cols })}
          style={{ marginLeft: metrics.left + metrics.pitch / 2 - RULER_TICK_INSET }}
        />
      )}
    </Box>
  );
}

/** "Row 3 reads 30 / 30 … nothing straddles a seam" (04b `127:135751`), from the rendered rows. */
export function NoteSeamSummary({ straddles }: { straddles: readonly SeamStraddle[] }) {
  const t = useTranslations("complexEditing");
  return (
    <Stack gap="1" data-slot="note-seam-summary" role="status">
      {straddles.length === 0 ? (
        <Text size="xs" tone="muted">
          {t("seamsClear")}
        </Text>
      ) : (
        straddles.map((s) => (
          <Text key={`${s.row}-${s.column}`} size="xs" tone="warning">
            {t("seamStraddle", { row: s.row, word: s.word, column: s.column })}
          </Text>
        ))
      )}
    </Stack>
  );
}

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

/**
 * C37 row bands in the template gutter (04b `126:149604`): an editor lens over
 * runs of non-blank rows, with Move up / Move down / Duplicate. Bands are
 * derived from the template on every render; the page stores no bands.
 */
export function RowBandGutter<A>({
  enabled,
  state,
  rows,
  editorRootRef,
  onChange,
}: {
  enabled: boolean;
  state: TemplateRowsState<A>;
  rows: number;
  /** The (relative) template container this gutter sits in; its left padding makes room. */
  editorRootRef: RefObject<HTMLElement | null>;
  onChange: (next: TemplateRowsState<A>) => void;
}) {
  const t = useTranslations("complexEditing");
  const gutterRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [boxes, setBoxes] = useState<LineBox[]>([]);
  const bands = useMemo(() => deriveRowBands(state.lines, rows), [state.lines, rows]);
  const lineCount = Math.min(rows, Math.max(state.lines.length, 1));

  useEffect(() => {
    const root = editorRootRef.current;
    const gutter = gutterRef.current;
    if (!enabled || !root || !gutter) return;
    let frame = 0;
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const next = measureLineBoxes(root, gutter, lineCount);
        setBoxes((previous) => (JSON.stringify(previous) === JSON.stringify(next) ? previous : next));
      });
    };
    measure();
    // The editor's own edits move rows; the gutter's re-renders must not re-trigger it.
    const mutations = new MutationObserver((records) => {
      if (records.some((record) => !gutter.contains(record.target))) measure();
    });
    mutations.observe(root, { childList: true, subtree: true, characterData: true });
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    resize?.observe(root);
    return () => {
      cancelAnimationFrame(frame);
      mutations.disconnect();
      resize?.disconnect();
    };
  }, [editorRootRef, lineCount, enabled]);

  if (!enabled) return null;

  const menu = (id: string): RowBandMenuItem[] => {
    const up = moveBand(state, bands, id, "up");
    const down = moveBand(state, bands, id, "down");
    const copy = duplicateBand(state, bands, id, rows);
    return [
      { id: "up", label: t("bandMoveUp"), disabled: !up, onSelect: () => up && onChange(up) },
      { id: "down", label: t("bandMoveDown"), disabled: !down, onSelect: () => down && onChange(down) },
      { id: "duplicate", label: t("bandDuplicate"), disabled: !copy, onSelect: () => copy && onChange(copy) },
    ];
  };

  return (
    <Box
      ref={gutterRef}
      role="list"
      aria-label={t("bandsLabel")}
      data-slot="row-band-gutter"
      className="absolute inset-y-0 left-0 w-36"
    >
      {bands.map((band, index) => {
        const top = boxes[band.start - 1]?.top;
        const last = boxes[band.end - 1];
        if (top === undefined || !last) return null;
        // A band's bracket runs down to the next band (over its trailing blank
        // rows, as 04b draws it), so a one-row band still fits its label.
        const nextTop = bands[index + 1] ? boxes[bands[index + 1].start - 1]?.top : undefined;
        const bottom = Math.max(last.top + last.height, (nextTop ?? last.top + last.height) - 4);
        return (
          <Box key={band.id} role="listitem" className="absolute inset-x-0" style={{ top }}>
            <RowBand
              className="w-full"
              style={{ height: Math.max(24, bottom - top) }}
              label={band.label ?? t("bandFallback", { start: band.start, end: band.end })}
              rows={[band.start, band.end]}
              formatRows={(start, end) =>
                start === end ? t("bandRow", { row: start }) : t("bandRows", { start, end })
              }
              selected={selected === band.id}
              onSelectedChange={(on) => setSelected(on ? band.id : null)}
              menu={menu(band.id)}
              menuLabel={t("bandMenu", { label: band.label ?? band.start })}
            />
          </Box>
        );
      })}
    </Box>
  );
}
