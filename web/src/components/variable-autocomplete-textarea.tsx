"use client";

import { Box, Text, Textarea } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";

import { api, type TemplateVariables } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface VariableSuggestion {
  token: string;
  description?: string;
  preview?: string;
}

interface VariableAutocompleteTextareaProps {
  value: string;
  onChange: (next: string) => void;
  /** Called whenever the known-variable list updates so the parent can validate the expression. */
  onKnownVariablesChange?: (knownTokens: Set<string>) => void;
  placeholder?: string;
  className?: string;
  id?: string;
  ariaLabel?: string;
  disabled?: boolean;
}

const IDENT_CHAR = /[A-Za-z0-9_.]/;
const MAX_SUGGESTIONS = 8;

function flattenVariables(data: TemplateVariables | undefined): VariableSuggestion[] {
  if (!data) return [];
  const out: VariableSuggestion[] = [];
  for (const [source, fields] of Object.entries(data.variables || {})) {
    for (const field of fields) {
      const token = `${source}.${field}`;
      const meta = data.variable_metadata?.[source]?.[field];
      out.push({ token, description: meta?.description, preview: meta?.preview });
    }
  }
  return out.sort((a, b) => a.token.localeCompare(b.token));
}

function findTokenAtCursor(text: string, caret: number): { start: number; end: number; token: string } {
  let start = caret;
  while (start > 0 && IDENT_CHAR.test(text[start - 1])) start -= 1;
  let end = caret;
  while (end < text.length && IDENT_CHAR.test(text[end])) end += 1;
  return { start, end, token: text.slice(start, end) };
}

/** True if the caret sits inside an unclosed string literal (single or double quotes). */
function cursorIsInString(text: string, caret: number): boolean {
  let inSingle = false;
  let inDouble = false;
  for (let i = 0; i < caret; i++) {
    const ch = text[i];
    if (ch === "\\") {
      // Skip escaped character.
      i += 1;
      continue;
    }
    if (ch === '"' && !inSingle) inDouble = !inDouble;
    else if (ch === "'" && !inDouble) inSingle = !inSingle;
  }
  return inSingle || inDouble;
}

export const VariableAutocompleteTextarea = forwardRef<HTMLTextAreaElement, VariableAutocompleteTextareaProps>(
  function VariableAutocompleteTextarea(
    { value, onChange, onKnownVariablesChange, placeholder, className, id, ariaLabel, disabled },
    ref,
  ) {
    const innerRef = useRef<HTMLTextAreaElement | null>(null);
    useImperativeHandle(ref, () => innerRef.current as HTMLTextAreaElement);

    const { data } = useQuery({
      queryKey: ["template-variables"],
      queryFn: () => api.getTemplateVariables(),
      staleTime: 60_000,
    });
    const allSuggestions = useMemo(() => flattenVariables(data), [data]);

    // Surface known variables to the parent for validation.
    useEffect(() => {
      if (!onKnownVariablesChange) return;
      onKnownVariablesChange(new Set(allSuggestions.map((s) => s.token)));
    }, [allSuggestions, onKnownVariablesChange]);

    const [open, setOpen] = useState(false);
    const [activeIndex, setActiveIndex] = useState(0);
    const [filterToken, setFilterToken] = useState("");
    const [tokenRange, setTokenRange] = useState<{ start: number; end: number }>({ start: 0, end: 0 });

    const filtered = useMemo(() => {
      if (!filterToken) return allSuggestions.slice(0, MAX_SUGGESTIONS);
      const lower = filterToken.toLowerCase();
      return allSuggestions.filter((s) => s.token.toLowerCase().includes(lower)).slice(0, MAX_SUGGESTIONS);
    }, [allSuggestions, filterToken]);

    // Keep the latest filtered/activeIndex in refs so keydown never sees stale state.
    const filteredRef = useRef(filtered);
    const activeIndexRef = useRef(activeIndex);
    const openRef = useRef(open);
    useEffect(() => {
      filteredRef.current = filtered;
    }, [filtered]);
    useEffect(() => {
      activeIndexRef.current = activeIndex;
    }, [activeIndex]);
    useEffect(() => {
      openRef.current = open;
    }, [open]);

    // While the popover is open, set a global flag so a parent Sheet/Dialog can
    // suppress its own Escape-to-close via its onEscapeKeyDown handler.
    useEffect(() => {
      const ATTR = "data-variable-autocomplete-open";
      if (open) document.documentElement.setAttribute(ATTR, "1");
      else document.documentElement.removeAttribute(ATTR);
      return () => document.documentElement.removeAttribute(ATTR);
    }, [open]);

    const refreshSuggestions = useCallback(() => {
      const el = innerRef.current;
      if (!el) return;
      const caret = el.selectionStart ?? 0;
      const text = el.value;
      if (cursorIsInString(text, caret)) {
        setOpen(false);
        return;
      }
      const { start, end, token } = findTokenAtCursor(text, caret);
      setTokenRange({ start, end });
      setFilterToken(token);
      setActiveIndex(0);
      setOpen(token.length > 0);
    }, []);

    useEffect(() => {
      if (open && filtered.length === 0) setOpen(false);
    }, [open, filtered.length]);

    const insertSuggestion = useCallback(
      (suggestion: VariableSuggestion) => {
        const el = innerRef.current;
        if (!el) return;
        const next = el.value.slice(0, tokenRange.start) + suggestion.token + el.value.slice(tokenRange.end);
        const newCaret = tokenRange.start + suggestion.token.length;
        onChange(next);
        setOpen(false);
        requestAnimationFrame(() => {
          el.focus();
          el.setSelectionRange(newCaret, newCaret);
        });
      },
      [onChange, tokenRange.start, tokenRange.end],
    );

    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (!openRef.current || filteredRef.current.length === 0) return;
        const filteredNow = filteredRef.current;
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setActiveIndex((i) => (i + 1) % filteredNow.length);
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          setActiveIndex((i) => (i - 1 + filteredNow.length) % filteredNow.length);
        } else if (e.key === "Enter" || e.key === "Tab") {
          e.preventDefault();
          insertSuggestion(filteredNow[activeIndexRef.current]);
        } else if (e.key === "Escape") {
          // Parent Sheet sees the global flag and skips closing itself.
          e.preventDefault();
          setOpen(false);
        }
      },
      [insertSuggestion],
    );

    return (
      <Box className="relative">
        <Textarea
          ref={innerRef}
          id={id}
          aria-label={ariaLabel}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            requestAnimationFrame(refreshSuggestions);
          }}
          onKeyDown={handleKeyDown}
          onKeyUp={(e) => {
            if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) refreshSuggestions();
          }}
          onClick={refreshSuggestions}
          onBlur={() => {
            // Delay so a click on a suggestion can still register.
            setTimeout(() => setOpen(false), 150);
          }}
          placeholder={placeholder}
          className={cn("font-mono text-sm min-h-[64px]", className)}
          disabled={disabled}
        />
        {open && filtered.length > 0 && (
          <Box
            role="listbox"
            className="absolute left-0 right-0 z-30 mt-1 max-h-64 overflow-auto rounded-md border bg-popover p-1 shadow-md"
          >
            {filtered.map((s, idx) => (
              <button
                type="button"
                key={s.token}
                role="option"
                aria-selected={idx === activeIndex}
                onMouseDown={(e) => {
                  e.preventDefault();
                  insertSuggestion(s);
                }}
                onMouseEnter={() => setActiveIndex(idx)}
                className={cn(
                  "flex w-full items-center justify-between gap-3 rounded px-2 py-1.5 text-left text-sm",
                  idx === activeIndex ? "bg-accent text-accent-foreground" : "hover:bg-accent/50",
                )}
              >
                <Text
                  as="span"
                  size="xs"
                  className={cn("font-mono", idx === activeIndex && "text-accent-foreground")}
                >
                  {s.token}
                </Text>
                {s.preview && (
                  <Text as="span" size="xs" tone="muted" className="truncate">
                    {s.preview.length > 20 ? `${s.preview.slice(0, 20)}…` : s.preview}
                  </Text>
                )}
              </button>
            ))}
          </Box>
        )}
      </Box>
    );
  },
);

export interface ExpressionLintFinding {
  kind: "strict-eq" | "unterminated-string" | "unbalanced-parens";
  message: string;
  /** When present, applying the fix returns a new expression string. */
  autoFix?: (expr: string) => string;
}

/**
 * Lightweight static checks for the FiestaBoard expression language.
 * Catches common mistakes that the server would otherwise reject at evaluation time.
 */
export function lintExpression(expression: string): ExpressionLintFinding[] {
  const findings: ExpressionLintFinding[] = [];
  // `===` isn't valid; the engine uses `=` or `==`. Offer one-click cleanup.
  if (/===/.test(expression)) {
    findings.push({
      kind: "strict-eq",
      message: "`===` isn't valid here — use `==` (or `=`)",
      autoFix: (e) => e.replace(/===/g, "=="),
    });
  }

  // Walk to detect unbalanced parens and unterminated strings (ignoring escapes
  // inside strings).
  let depth = 0;
  let inSingle = false;
  let inDouble = false;
  for (let i = 0; i < expression.length; i++) {
    const ch = expression[i];
    if (ch === "\\") {
      i += 1;
      continue;
    }
    if (ch === '"' && !inSingle) inDouble = !inDouble;
    else if (ch === "'" && !inDouble) inSingle = !inSingle;
    else if (!inSingle && !inDouble) {
      if (ch === "(") depth += 1;
      else if (ch === ")") depth -= 1;
      if (depth < 0) break; // Closing without an opener.
    }
  }
  if (depth !== 0) {
    findings.push({
      kind: "unbalanced-parens",
      message: depth > 0 ? "Unbalanced parentheses: missing `)`" : "Unbalanced parentheses: stray `)`",
    });
  }
  if (inSingle || inDouble) {
    findings.push({
      kind: "unterminated-string",
      message: `Unterminated ${inDouble ? '"' : "'"} string literal`,
    });
  }

  return findings;
}

/**
 * Extract identifier tokens (e.g. `weather.temperature`) that look like variable references
 * from an expression. Ignores anything inside single/double-quoted string literals.
 */
export function extractReferencedVariables(expression: string): string[] {
  const tokens: string[] = [];
  let inSingle = false;
  let inDouble = false;
  let i = 0;
  while (i < expression.length) {
    const ch = expression[i];
    if (ch === "\\") {
      i += 2;
      continue;
    }
    if (ch === '"' && !inSingle) {
      inDouble = !inDouble;
      i += 1;
      continue;
    }
    if (ch === "'" && !inDouble) {
      inSingle = !inSingle;
      i += 1;
      continue;
    }
    if (!inSingle && !inDouble && IDENT_CHAR.test(ch)) {
      let j = i;
      while (j < expression.length && IDENT_CHAR.test(expression[j])) j += 1;
      const tok = expression.slice(i, j);
      // Only dotted identifiers look like variable references; bare words could be keywords/numbers.
      if (tok.includes(".") && !/^\d/.test(tok)) tokens.push(tok);
      i = j;
      continue;
    }
    i += 1;
  }
  return tokens;
}
