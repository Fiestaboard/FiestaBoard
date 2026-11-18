"use client";

import { Box, Stack, Text, Textarea } from "@fiestaboard/ui";
import { forwardRef, type ReactNode, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

export interface PlainTextEditorHandle {
  /** Insert literal template syntax at the current selection and return focus. */
  insert: (text: string) => void;
  undo: () => void;
  redo: () => void;
}

export interface PlainTextHistoryState {
  canUndo: boolean;
  canRedo: boolean;
}

interface TextSnapshot {
  value: string;
  start: number;
  end: number;
}

interface PlainTextEditorProps {
  /** id on the underlying textarea, so a caller can point a <Label htmlFor> at it. */
  id?: string;
  value: string;
  onChange: (value: string) => void;
  onFocus?: () => void;
  onHistoryChange?: (state: PlainTextHistoryState) => void;
  placeholder?: string;
  className?: string;
  boardLines?: number;
  boardWidth?: number;
  /**
   * Read-only markers by 0-based line (`{canvas:sky}` where a pixel canvas
   * starts), shown beside the line and never part of the text.
   */
  lineMarkers?: Record<number, string[]>;
  /** Tooltip / accessible description for a marker. */
  lineMarkerTitle?: string;
  /**
   * Replaces the line counter and the template-syntax tips with the caller's
   * own one-line helper (Compose a message, 07a `310:20283`). Omit for the
   * template editor's full help.
   */
  help?: ReactNode;
}

/**
 * Plain text code editor for template editing.
 * No line-count restrictions — a validation warning is shown when over the limit.
 */
export const PlainTextEditor = forwardRef<PlainTextEditorHandle, PlainTextEditorProps>(function PlainTextEditor(
  {
    id,
    value,
    onChange,
    onFocus,
    onHistoryChange,
    placeholder,
    className,
    boardLines = 6,
    boardWidth = 22,
    lineMarkers,
    lineMarkerTitle,
    help,
  }: PlainTextEditorProps,
  ref,
) {
  const t = useTranslations("plainTextEditor");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineNumbersRef = useRef<HTMLDivElement>(null);
  const markersRef = useRef<HTMLElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const effectivePlaceholder = placeholder ?? t("placeholder");
  const [lineHeights, setLineHeights] = useState<number[]>([]);
  const history = useRef({
    value,
    undo: [] as TextSnapshot[],
    redo: [] as TextSnapshot[],
    selection: { start: 0, end: 0 },
    before: null as TextSnapshot | null,
    composition: null as TextSnapshot | null,
    frame: null as number | null,
    availability: { canUndo: false, canRedo: false },
  });
  const snapshot = useCallback(
    (): TextSnapshot => ({
      value: history.current.value,
      start: textareaRef.current?.selectionStart ?? history.current.selection.start,
      end: textareaRef.current?.selectionEnd ?? history.current.selection.end,
    }),
    [],
  );
  const restoreSelection = useCallback((next: TextSnapshot) => {
    const state = history.current;
    if (state.frame !== null) cancelAnimationFrame(state.frame);
    state.selection = { start: next.start, end: next.end };
    state.frame = requestAnimationFrame(() => {
      state.frame = null;
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(next.start, next.end);
    });
  }, []);
  const reportHistory = useCallback(() => {
    const state = history.current;
    const canUndo = state.undo.length > 0;
    const canRedo = state.redo.length > 0;
    if (state.availability.canUndo !== canUndo || state.availability.canRedo !== canRedo) {
      state.availability = { canUndo, canRedo };
    }
    onHistoryChange?.(state.availability);
  }, [onHistoryChange]);
  const commit = useCallback(
    (next: string, before?: TextSnapshot) => {
      const state = history.current;
      const previous = before ?? state.before ?? { value: state.value, ...state.selection };
      if (previous.value !== next) {
        state.undo.push(previous);
        if (state.undo.length > 100) state.undo.shift();
        state.redo = [];
      }
      state.value = next;
      state.before = null;
      state.selection = {
        start: textareaRef.current?.selectionStart ?? next.length,
        end: textareaRef.current?.selectionEnd ?? next.length,
      };
      onChange(next);
      reportHistory();
    },
    [onChange, reportHistory],
  );
  const travel = useCallback(
    (direction: "undo" | "redo") => {
      const state = history.current;
      if (state.composition) return;
      const next = state[direction].pop();
      if (!next) return;
      state[direction === "undo" ? "redo" : "undo"].push(state.before ?? snapshot());
      state.value = next.value;
      state.before = null;
      onChange(next.value);
      restoreSelection(next);
      reportHistory();
    },
    [onChange, reportHistory, restoreSelection, snapshot],
  );

  useEffect(() => {
    reportHistory();
  }, [reportHistory]);

  useEffect(() => {
    const state = history.current;
    if (state.value === value) return;
    // A different controlled document starts a new history; never undo into a
    // prior page, restored draft or external assistant replacement.
    if (state.frame !== null) cancelAnimationFrame(state.frame);
    state.frame = null;
    state.value = value;
    state.undo = [];
    state.redo = [];
    state.before = null;
    state.composition = null;
    state.selection = { start: 0, end: 0 };
    reportHistory();
  }, [reportHistory, value]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    // React's normalized before-input event does not consistently expose the
    // native history input types, including browser menu undo/redo.
    const beforeInput = (event: InputEvent) => {
      if (event.inputType === "historyUndo" || event.inputType === "historyRedo") {
        if (history.current.composition) return;
        if (!event.cancelable) {
          // The browser will mutate the DOM and dispatch input; handle the
          // controlled travel once there, retaining the pre-mutation caret.
          history.current.before = snapshot();
          return;
        }
        event.preventDefault();
        travel(event.inputType === "historyUndo" ? "undo" : "redo");
      } else history.current.before = snapshot();
    };
    textarea.addEventListener("beforeinput", beforeInput);
    return () => textarea.removeEventListener("beforeinput", beforeInput);
  }, [snapshot, travel]);

  useEffect(
    () => () => {
      if (history.current.frame !== null) cancelAnimationFrame(history.current.frame);
    },
    [],
  );

  useImperativeHandle(
    ref,
    () => ({
      insert(text) {
        const textarea = textareaRef.current;
        if (!textarea) return;
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const next = history.current.value.slice(0, start) + text + history.current.value.slice(end);
        commit(next, snapshot());
        restoreSelection({ value: next, start: start + text.length, end: start + text.length });
      },
      undo: () => travel("undo"),
      redo: () => travel("redo"),
    }),
    [commit, restoreSelection, snapshot, travel],
  );

  const computeLineHeights = useCallback(() => {
    const mirror = mirrorRef.current;
    const textarea = textareaRef.current;
    if (!mirror || !textarea) return;

    // Match mirror width and font to the textarea so wrapping is identical
    const style = window.getComputedStyle(textarea);
    mirror.style.width = `${textarea.clientWidth}px`;
    mirror.style.fontFamily = style.fontFamily;
    mirror.style.fontSize = style.fontSize;
    mirror.style.lineHeight = style.lineHeight;
    mirror.style.paddingLeft = style.paddingLeft;
    mirror.style.paddingRight = style.paddingRight;

    const lines = value.split("\n");

    // Reuse existing child divs; add or remove to match line count
    while (mirror.children.length < lines.length) {
      mirror.appendChild(document.createElement("div"));
    }
    while (mirror.children.length > lines.length) {
      mirror.removeChild(mirror.lastChild!);
    }

    const heights: number[] = [];
    for (let i = 0; i < lines.length; i++) {
      const div = mirror.children[i] as HTMLDivElement;
      // Use non-breaking space for empty lines so they render with full line height
      div.textContent = lines[i] || " ";
      heights.push(div.offsetHeight);
    }

    setLineHeights(heights);

    // Auto-resize textarea height
    textarea.style.height = "auto";
    textarea.style.height = `${Math.max(textarea.scrollHeight, boardLines * 24)}px`;
  }, [value, boardLines]);

  useEffect(() => {
    computeLineHeights();
  }, [computeLineHeights]);

  // Re-measure when the textarea is resized (e.g. window resize changes available width)
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const observer = new ResizeObserver(computeLineHeights);
    observer.observe(textarea);
    return () => observer.disconnect();
  }, [computeLineHeights]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const inputType = (e.nativeEvent as InputEvent).inputType;
    if (inputType === "historyUndo" || inputType === "historyRedo") {
      travel(inputType === "historyUndo" ? "undo" : "redo");
    } else if (history.current.composition) {
      history.current.value = e.target.value;
      onChange(e.target.value);
    } else commit(e.target.value);
  };

  const handleScroll = (e: React.UIEvent<HTMLTextAreaElement>) => {
    if (lineNumbersRef.current) {
      lineNumbersRef.current.scrollTop = e.currentTarget.scrollTop;
    }
    if (markersRef.current) {
      markersRef.current.scrollTop = e.currentTarget.scrollTop;
    }
  };

  const lineCount = value.split("\n").length;
  const hasMarkers = !!lineMarkers && Object.keys(lineMarkers).length > 0;
  const isOverLimit = lineCount > boardLines;

  const gutterNumbers =
    lineHeights.length === lineCount
      ? lineHeights.map((h, i) => ({ height: h, label: i + 1 }))
      : Array.from({ length: lineCount }, (_, i) => ({ height: 24, label: i + 1 }));

  return (
    <Box className={cn("relative", className)}>
      {/* Hidden mirror div — measures actual wrapped height of each logical line */}
      <Box
        ref={mirrorRef}
        aria-hidden="true"
        style={{
          position: "absolute",
          top: "-9999px",
          left: "-9999px",
          visibility: "hidden",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          overflowWrap: "anywhere",
          overflow: "hidden",
          boxSizing: "border-box",
        }}
      />

      {/* Editor with line numbers */}
      <Box
        className={cn(
          "flex rounded-md border overflow-hidden bg-background",
          "focus-within:outline-none focus-within:ring-1 focus-within:ring-ring",
          isOverLimit && "border-warning focus-within:ring-warning",
        )}
      >
        {/* Line numbers gutter */}
        <Box
          ref={lineNumbersRef}
          className="select-none overflow-hidden bg-muted/40 border-r shrink-0 text-right"
          style={{
            fontSize: "0.75rem",
            lineHeight: "1.5rem",
            color: "var(--muted-foreground)",
            opacity: 0.7,
            paddingTop: "0.5rem",
            paddingBottom: "0.5rem",
            paddingLeft: "0.375rem",
            paddingRight: "0.375rem",
            minWidth: "2rem",
          }}
          aria-hidden="true"
        >
          {gutterNumbers.map(({ height, label }) => (
            <Box
              key={label}
              style={{
                height: `${height}px`,
                display: "flex",
                alignItems: "flex-start",
                justifyContent: "flex-end",
                paddingTop: "0.15rem",
              }}
            >
              {label}
            </Box>
          ))}
        </Box>

        {/* Textarea — border handled by wrapper above */}
        <Textarea
          id={id}
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onSelect={() => {
            history.current.selection = {
              start: textareaRef.current?.selectionStart ?? 0,
              end: textareaRef.current?.selectionEnd ?? 0,
            };
          }}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing || history.current.composition) return;
            if ((event.ctrlKey || event.metaKey) && !event.altKey && ["z", "y"].includes(event.key.toLowerCase())) {
              event.preventDefault();
              travel(event.key.toLowerCase() === "y" || event.shiftKey ? "redo" : "undo");
            } else history.current.before = snapshot();
          }}
          onCompositionStart={() => {
            history.current.composition = snapshot();
          }}
          onCompositionEnd={() => {
            const before = history.current.composition;
            history.current.composition = null;
            if (before && textareaRef.current) commit(textareaRef.current.value, before);
          }}
          onFocus={onFocus}
          onScroll={handleScroll}
          placeholder={effectivePlaceholder}
          className={cn(
            "font-mono resize-none overflow-y-auto flex-1",
            "border-0 rounded-none shadow-none",
            "focus-visible:ring-0 focus-visible:ring-offset-0",
          )}
          rows={boardLines}
          style={{
            minHeight: `${boardLines * 1.5}rem`,
            lineHeight: "1.5rem",
          }}
        />

        {/* Read-only markers (a pixel canvas's first row): beside the text, never in it */}
        {hasMarkers && (
          <Box
            ref={markersRef}
            data-testid="line-markers"
            className="select-none overflow-hidden border-l bg-muted/40 shrink-0 font-mono"
            style={{ fontSize: "0.7rem", lineHeight: "1.5rem", paddingTop: "0.5rem", paddingBottom: "0.5rem" }}
          >
            {gutterNumbers.map(({ height, label }) => (
              <Box key={label} style={{ height: `${height}px` }} className="px-1.5 text-muted-foreground">
                {(lineMarkers?.[label - 1] ?? []).map((marker) => (
                  <Text as="span" size="xs" key={marker} title={lineMarkerTitle} className="mr-1 font-mono">
                    {marker}
                  </Text>
                ))}
              </Box>
            ))}
          </Box>
        )}
      </Box>

      {help !== undefined ? (
        help
      ) : (
        <>
          {/* Line counter */}
          <Text size="xs" className={cn("mt-1", isOverLimit ? "text-warning font-medium" : "text-muted-foreground")}>
            {t("lineCount", { current: lineCount, total: boardLines })}
            {isOverLimit && ` ${t("exceedsLimit", { limit: boardLines })}`}
          </Text>

          {/* Helper text */}
          <Stack gap="1" className="mt-2">
            <Text size="xs" tone="muted">
              • {t("charsPerLine", { width: boardWidth })}
            </Text>
            <Text size="xs" tone="muted">
              • {t("templateSyntaxIntro")} {"{{variable}}"}, {"{{red}}"}, {"{{fill_space}}"}
            </Text>
            <Text size="xs" tone="muted">
              • {t("alignmentPrefixesIntro")} {"{left}"}, {"{center}"}, {"{right}"}
            </Text>
            <Text size="xs" tone="muted">
              • {t("wrapPrefixIntro")} {"{wrap}"}
            </Text>
          </Stack>
        </>
      )}
    </Box>
  );
});
