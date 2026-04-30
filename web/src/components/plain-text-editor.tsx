"use client";

import { useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Textarea } from "@/components/ui/textarea";
import { useTranslations } from "next-intl";

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
  const effectivePlaceholder = placeholder ?? t("placeholder");

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
        placeholder={effectivePlaceholder}
        className={cn(
          "font-mono resize-none overflow-y-auto",
          isOverLimit && "border-warning focus-visible:ring-warning"
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
        isOverLimit ? "text-warning font-medium" : "text-muted-foreground"
      )}>
        {t("lineCount", { current: lineCount, total: boardLines })}
        {isOverLimit && ` ${t("exceedsLimit", { limit: boardLines })}`}
      </div>

      {/* Helper text */}
      <div className="mt-2 text-xs text-muted-foreground space-y-1">
        <p>• {t("charsPerLine", { width: boardWidth })}</p>
        <p>• {t("templateSyntaxIntro")} {'{{variable}}'}, {'{{red}}'}, {'{{fill_space}}'}</p>
        <p>• {t("alignmentPrefixesIntro")} {'{left}'}, {'{center}'}, {'{right}'}</p>
        <p>• {t("wrapPrefixIntro")} {'{wrap}'}</p>
      </div>
    </div>
  );
}
