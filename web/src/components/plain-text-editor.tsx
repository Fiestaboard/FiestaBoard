"use client";

import { useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Textarea } from "@/components/ui/textarea";

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
  placeholder = "Type your template text...",
  className,
  boardLines = 6,
  boardWidth = 22,
}: PlainTextEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.max(textarea.scrollHeight, boardLines * 24)}px`;
    }
  }, [value, boardLines]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value);
  };

  const lineCount = value.split('\n').length;
  const isOverLimit = lineCount > boardLines;

  return (
    <div className={cn("relative", className)}>
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onFocus={onFocus}
        placeholder={placeholder}
        className={cn(
          "font-mono resize-none overflow-y-auto",
          isOverLimit && "border-amber-500 focus-visible:ring-amber-500"
        )}
        rows={boardLines}
        style={{
          minHeight: `${boardLines * 1.5}rem`,
          lineHeight: '1.5rem',
        }}
      />

      {/* Line counter */}
      <div className={cn(
        "mt-1 text-xs",
        isOverLimit ? "text-amber-600 dark:text-amber-400 font-medium" : "text-muted-foreground"
      )}>
        {lineCount} / {boardLines} lines
        {isOverLimit && ` — exceeds the ${boardLines}-line board limit`}
      </div>

      {/* Helper text */}
      <div className="mt-2 text-xs text-muted-foreground space-y-1">
        <p>• {boardWidth} characters per line recommended</p>
        <p>• Use template syntax: {'{{variable}}'}, {'{{red}}'}, {'{{fill_space}}'}</p>
        <p>• Alignment prefixes: {'{left}'}, {'{center}'}, {'{right}'}</p>
        <p>• Wrap prefix: {'{wrap}'}</p>
      </div>
    </div>
  );
}
