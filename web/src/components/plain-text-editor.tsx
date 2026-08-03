"use client";

import { Box, Stack, Text, Textarea } from "@fiestaboard/ui";
import { useCallback, useEffect, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

interface PlainTextEditorProps {
  value: string;
  onChange: (value: string) => void;
  onFocus?: () => void;
  placeholder?: string;
  className?: string;
  boardLines?: number;
  boardWidth?: number;
}

/**
 * Plain text code editor for template editing.
 * No line-count restrictions — a validation warning is shown when over the limit.
 */
export function PlainTextEditor({
  value,
  onChange,
  onFocus,
  placeholder,
  className,
  boardLines = 6,
  boardWidth = 22,
}: PlainTextEditorProps) {
  const t = useTranslations("plainTextEditor");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineNumbersRef = useRef<HTMLDivElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const effectivePlaceholder = placeholder ?? t("placeholder");
  const [lineHeights, setLineHeights] = useState<number[]>([]);

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
    onChange(e.target.value);
  };

  const handleScroll = (e: React.UIEvent<HTMLTextAreaElement>) => {
    if (lineNumbersRef.current) {
      lineNumbersRef.current.scrollTop = e.currentTarget.scrollTop;
    }
  };

  const lineCount = value.split("\n").length;
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
          ref={textareaRef}
          value={value}
          onChange={handleChange}
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
      </Box>

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
    </Box>
  );
}
