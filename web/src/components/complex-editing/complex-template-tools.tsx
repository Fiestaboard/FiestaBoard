"use client";

import {
  Box,
  ColumnRuler,
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
  bandText,
  deriveRowBands,
  duplicateBand,
  moveBand,
  noteSeamMarks,
  type SeamStraddle,
  type TemplateRowsState,
} from "@/lib/complex-editing";
import { type LineBox, measureLineBoxes } from "@/lib/complex-editing-dom";
import { cn } from "@/lib/utils";

const RULER_TICK_INSET = 14;

/**
 * The template pane's header lens: Note focus with a seam ruler (note array,
 * 04b `127:135751`). A big board has none: the card header's caret readout
 * replaced the "Row · Col" Go to pill and its caption (editor UX UX-3-2;
 * Figma 184:159319 draws neither).
 */
export function ComplexTemplateHeader({
  complex,
  editorRootRef,
}: {
  complex: ComplexEditing;
  /** The template editor's container: the ruler lines up with its text. */
  editorRootRef: RefObject<HTMLElement | null>;
  /** Unused since the Go to pill left (UX-3-2); kept until the host stops passing it. */
  onGo?: (position: GoToCellPosition) => void;
}) {
  const t = useTranslations("complexEditing");
  if (!complex.noteArray) return null;
  return (
    <Stack gap="2" data-slot="complex-template-header">
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
    // The template editor mounts lazily and reflows: follow it as well.
    const root = editorRootRef.current;
    const mutations = new MutationObserver(measure);
    if (root) mutations.observe(root, { childList: true, subtree: true });
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    if (boxRef.current) resize?.observe(boxRef.current);
    if (root) resize?.observe(root);
    return () => {
      mutations.disconnect();
      resize?.disconnect();
    };
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

/** The template's editable text: TipTap's ProseMirror element (what `measureLineBoxes` reads). */
const TEMPLATE_TEXT = '[contenteditable="true"], .ProseMirror';

/** Whether an element takes part in layout (not under display:none). */
function isRendered(element: Element | null): boolean {
  if (element === null) return false;
  // Without checkVisibility (jsdom, old engines) assume it is: measuring is still correct.
  return typeof element.checkVisibility === "function" ? element.checkVisibility() : true;
}

function sameBoxes(a: readonly LineBox[], b: readonly LineBox[]): boolean {
  return a.length === b.length && a.every((box, i) => box.top === b[i].top && box.height === b[i].height);
}

/** Below this band height the row range is dropped and only the label shows (UX-3-1). */
const BAND_META_MIN_HEIGHT = 36;

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
    let editable: Element | null = root.querySelector(TEMPLATE_TEXT);
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        // Hidden (draw mode keeps the editor mounted under display:none): a
        // measurement would force a layout of the whole page for nothing.
        // The root's ResizeObserver fires again when the editor reappears
        // (BB-E-31).
        if (!isRendered(root.querySelector(TEMPLATE_TEXT))) return;
        const next = measureLineBoxes(root, gutter, lineCount);
        setBoxes((previous) => (sameBoxes(previous, next) ? previous : next));
      });
    };
    measure();
    // Only the template text moves rows: the gutter's own re-renders, the
    // placeholder and anything else under the root must not re-measure it
    // (BB-E-31: every unrelated mutation forced a full layout per frame).
    const mutations = new MutationObserver((records) => {
      const current = root.querySelector(TEMPLATE_TEXT);
      const remounted = current !== editable;
      editable = current;
      if (remounted || records.some((record) => current?.contains(record.target))) measure();
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
        // Clamped to the band (UX-3-1): never taller than the rows it brackets,
        // so neighbours never overlap; the label is one line with an
        // ellipsis and its full text on hover.
        const height = Math.max(20, bottom - top);
        const rowsText =
          band.start === band.end
            ? t("bandRow", { row: band.start })
            : t("bandRows", { start: band.start, end: band.end });
        // An unnamed band is named by its rows; the row line would repeat it.
        const label = band.label ?? rowsText;
        return (
          <Box key={band.id} role="listitem" className="absolute inset-x-0" style={{ top }}>
            <RowBand
              data-testid="row-band"
              title={
                band.label ? `${bandText(state.lines[band.start - 1] ?? "") ?? band.label} · ${rowsText}` : rowsText
              }
              className={cn(
                "w-full min-h-0 overflow-hidden",
                "[&_[data-slot=row-band-label]]:truncate [&_[data-slot=row-band-meta]]:truncate",
                height < BAND_META_MIN_HEIGHT && "[&_[data-slot=row-band-meta]]:hidden",
              )}
              style={{ height }}
              label={label}
              meta={band.label ? undefined : ""}
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
