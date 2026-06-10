/**
 * FormulaEditorPanel — tabbed formula expression editor.
 *
 * Used in two contexts:
 *  1. Toolbar "Formulas" button  (mode="create") — Confirm button reads "Insert"
 *  2. Formula pill click          (mode="edit")   — Confirm button reads "Done", Cancel shown
 *
 * Tabs:
 *  - Functions: collapsible, by category — click scaffolds NAME() into the input
 *  - Variables: VariablePickerContent adapter — click inserts bare token at cursor
 */
"use client";

import { history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { HighlightStyle, StreamLanguage, syntaxHighlighting } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { tags } from "@lezer/highlight";
import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  ArrowLeftRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  GitBranch,
  Hash,
  Loader2,
  Palette,
  Type as TypeIcon,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

import { VariablePickerContent } from "./VariablePickerContent";

// ─── Formula pretty-printer ────────────────────────────────────────────────────

/** Expand a flat expression to a multi-line, indented string for display. */
function formatFormula(expr: string): string {
  let result = "";
  let depth = 0;
  let inString = false;
  let skipSpaces = false;
  const IND = "  ";

  for (let i = 0; i < expr.length; i++) {
    const ch = expr[i];

    if (inString) {
      result += ch;
      if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') {
      inString = true;
      skipSpaces = false;
      result += ch;
      continue;
    }

    if (skipSpaces && ch === " ") continue;
    skipSpaces = false;

    if (ch === "(") {
      depth++;
      result += "(\n" + IND.repeat(depth);
      skipSpaces = true;
    } else if (ch === ")") {
      depth--;
      result += "\n" + IND.repeat(depth) + ")";
    } else if (ch === ",") {
      result += ",\n" + IND.repeat(depth);
      skipSpaces = true;
    } else {
      result += ch;
    }
  }

  return result.trim();
}

/** Collapse a formatted expression back to a flat single-line string. */
function unformatFormula(str: string): string {
  let result = "";
  let inString = false;
  let prevWasNewline = false;

  for (const ch of str) {
    if (inString) {
      result += ch;
      if (ch === '"') inString = false;
      prevWasNewline = false;
    } else if (ch === '"') {
      inString = true;
      result += ch;
      prevWasNewline = false;
    } else if (ch === "\n") {
      prevWasNewline = true;
    } else if (ch === " " && prevWasNewline) {
      // skip indentation spaces after newlines
    } else {
      result += ch;
      prevWasNewline = false;
    }
  }

  return result.trim();
}

// ─── CodeMirror language + theme ──────────────────────────────────────────────

const formulaStreamLang = StreamLanguage.define({
  token(stream) {
    if (stream.eatSpace()) return null;
    if (stream.match(/"[^"]*"/)) return "string";
    if (stream.match(/\d+\.?\d*/)) return "number";
    // Lowercase variable path (e.g. date_time.hour, weather.temperature)
    if (stream.match(/[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*/)) return "variable";
    // Function name (uppercase, e.g. IF, COLOR, AND)
    if (stream.match(/[A-Z][A-Z0-9_]*/)) return "function";
    // Comparison + arithmetic operators
    if (stream.match(/[<>]=?|[!=]=|[+\-*/]/)) return "operator";
    // Parens and commas
    if (stream.match(/[(),]/)) return "punctuation";
    stream.next();
    return null;
  },
  tokenTable: {
    string: tags.string,
    number: tags.number,
    variable: tags.variableName,
    function: tags.keyword,
    operator: tags.operator,
    punctuation: tags.punctuation,
  },
});

const formulaHighlighter = HighlightStyle.define([
  { tag: tags.keyword, color: "#8b5cf6", fontWeight: "600" }, // functions — violet
  { tag: tags.string, color: "#16a34a" }, // strings   — green
  { tag: tags.number, color: "#ea580c" }, // numbers   — orange
  { tag: tags.variableName, color: "#0284c7" }, // variables — sky
  { tag: tags.operator, color: "hsl(var(--muted-foreground))" },
  { tag: tags.punctuation, color: "hsl(var(--muted-foreground))" },
]);

const formulaBaseTheme = EditorView.theme({
  "&": {
    fontSize: "0.75rem",
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Courier New", monospace',
    background: "hsl(var(--background))",
    height: "100%",
  },
  ".cm-scroller": { overflow: "auto" },
  ".cm-content": {
    padding: "0.375rem 0.625rem",
    caretColor: "hsl(var(--foreground))",
    color: "hsl(var(--foreground))",
    minHeight: "5rem",
  },
  ".cm-focused": { outline: "none" },
  ".cm-line": { padding: "0" },
  ".cm-cursor, .cm-dropCursor": {
    borderLeftColor: "hsl(var(--foreground))",
  },
  ".cm-selectionBackground": {
    background: "hsl(var(--muted)) !important",
  },
  "&.cm-focused .cm-selectionBackground": {
    background: "hsl(var(--accent)) !important",
  },
  ".cm-gutters": { display: "none" },
  ".cm-placeholder": { color: "hsl(var(--muted-foreground))" },
});

// ─── Category metadata ────────────────────────────────────────────────────────

const CATEGORY_ORDER = ["logic", "math", "text", "convert", "color"];

const CATEGORY_META: Record<string, { icon: LucideIcon; text: string; border: string }> = {
  logic: { icon: GitBranch, text: "text-violet-400", border: "border-l-violet-400/60" },
  math: { icon: Hash, text: "text-emerald-400", border: "border-l-emerald-400/60" },
  text: { icon: TypeIcon, text: "text-sky-400", border: "border-l-sky-400/60" },
  convert: { icon: ArrowLeftRight, text: "text-amber-400", border: "border-l-amber-400/60" },
  color: { icon: Palette, text: "text-pink-400", border: "border-l-pink-400/60" },
};

// ─── Props ────────────────────────────────────────────────────────────────────

interface FormulaEditorPanelProps {
  /** Pre-populated expression body (no {{= }}). Used in edit mode. */
  initialExpr?: string;
  /** "create" → Insert button; "edit" → Done button + Cancel */
  mode: "create" | "edit";
  /** Called with the bare expression when the user confirms. */
  onConfirm: (expr: string) => void;
  /** Called when the user cancels (edit mode only). */
  onCancel?: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function FormulaEditorPanel({ initialExpr = "", mode, onConfirm, onCancel }: FormulaEditorPanelProps) {
  const t = useTranslations("formulaEditor");
  const categoryLabels: Record<string, string> = {
    logic: t("categoryLogic"),
    math: t("categoryMath"),
    text: t("categoryText"),
    convert: t("categoryConversion"),
    color: t("categoryColor"),
  };
  const [expr, setExpr] = useState(initialExpr);
  const [validationState, setValidationState] = useState<"idle" | "validating" | "valid" | "invalid">(
    initialExpr ? "validating" : "idle",
  );
  const [errors, setErrors] = useState<string[]>([]);
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());

  // CodeMirror refs
  const editorContainerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestExprRef = useRef(expr);
  latestExprRef.current = expr;

  const lastValidExprRef = useRef<string | null>(null);

  // Always-current snapshot of state for use inside CodeMirror keybinding handlers
  const latestStateRef = useRef({ expr, validationState });
  latestStateRef.current = { expr, validationState };

  // ─── Fetch built-in function signatures ──────────────────────────────────

  const { data: fnData, isLoading: loadingFns } = useQuery({
    queryKey: ["formula-functions"],
    queryFn: api.getFormulaFunctions,
    staleTime: Infinity,
  });

  // ─── Debounced validation ─────────────────────────────────────────────────

  const validate = useCallback((expression: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = expression.trim();
    if (!trimmed) {
      lastValidExprRef.current = null;
      setValidationState("idle");
      setErrors([]);
      return;
    }

    setValidationState("validating");

    debounceRef.current = setTimeout(async () => {
      if (latestExprRef.current.trim() !== trimmed) return;

      try {
        const result = await api.validateTemplate(`{{= ${trimmed} }}`);
        if (latestExprRef.current.trim() !== trimmed) return;

        if (result.valid) {
          lastValidExprRef.current = trimmed;
          setValidationState("valid");
          setErrors([]);
        } else {
          lastValidExprRef.current = null;
          setValidationState("invalid");
          setErrors(result.errors.map((e) => e.message.replace(/^Formula\s+/, "")));
        }
      } catch {
        setValidationState("idle");
        setErrors([]);
      }
    }, 300);
  }, []);

  useEffect(() => {
    validate(expr);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [expr, validate]);

  // ─── CodeMirror initialisation ────────────────────────────────────────────

  useEffect(() => {
    if (!editorContainerRef.current) return;

    const view = new EditorView({
      state: EditorState.create({
        doc: formatFormula(initialExpr),
        extensions: [
          formulaStreamLang,
          syntaxHighlighting(formulaHighlighter),
          formulaBaseTheme,
          history(),
          EditorView.lineWrapping,
          keymap.of([
            ...historyKeymap,
            indentWithTab,
            {
              key: "Mod-Enter",
              run: () => {
                const { expr: e, validationState: vs } = latestStateRef.current;
                const trimmed = e.trim();
                if (!trimmed || vs !== "valid" || lastValidExprRef.current !== trimmed) return false;
                onConfirm(trimmed);
                return true;
              },
            },
          ]),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged) return;
            const raw = unformatFormula(update.state.doc.toString());
            setExpr(raw);
          }),
          EditorView.domEventHandlers({
            // Prevent clicks inside the editor from bubbling up to the pill/editor
            mousedown: (e) => e.stopPropagation(),
          }),
        ],
      }),
      parent: editorContainerRef.current,
    });

    viewRef.current = view;
    view.focus();
    if (mode === "edit" && initialExpr) {
      view.dispatch({
        selection: { anchor: 0, head: view.state.doc.length },
      });
    }

    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push external expr changes (function/variable clicks) into the editor
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const currentRaw = unformatFormula(view.state.doc.toString());
    if (currentRaw === expr) return;

    const formatted = formatFormula(expr);
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: formatted },
      selection: { anchor: formatted.length },
    });
  }, [expr]);

  // ─── Handlers ─────────────────────────────────────────────────────────────

  const handleConfirm = () => {
    const trimmed = expr.trim();
    if (!trimmed || validationState !== "valid" || lastValidExprRef.current !== trimmed) return;
    onConfirm(trimmed);
  };

  // Scaffold a function call into the editor at the current cursor
  const handleFunctionClick = (name: string) => {
    const scaffold = `${name}()`;
    const view = viewRef.current;
    if (!view) return;

    const formatted = formatFormula(scaffold);
    // Place cursor on the inner line (between opening paren and closing paren)
    const firstNewline = formatted.indexOf("\n");
    const innerEnd = firstNewline >= 0 ? formatted.indexOf("\n", firstNewline + 1) : -1;
    const cursorPos = innerEnd >= 0 ? innerEnd : formatted.length;

    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: formatted },
      selection: { anchor: cursorPos },
    });
    view.focus();
    setExpr(scaffold);
  };

  // Insert a variable token at the current cursor position in the editor
  const handleVariableInsert = (variable: string) => {
    const token = variable.replace(/^\{\{/, "").replace(/\}\}$/, "");
    const view = viewRef.current;
    if (!view) return;

    const cursor = view.state.selection.main.head;
    view.dispatch({
      changes: { from: cursor, to: cursor, insert: token },
      selection: { anchor: cursor + token.length },
    });
    view.focus();
    const raw = unformatFormula(view.state.doc.toString());
    setExpr(raw);
  };

  const toggleCategory = (cat: string) => {
    setCollapsedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const isConfirmDisabled = !expr.trim() || validationState !== "valid" || lastValidExprRef.current !== expr.trim();

  // ─── Group functions by category ─────────────────────────────────────────

  const grouped: Record<string, Array<{ name: string; signature: string; summary: string }>> = {};
  if (fnData?.functions) {
    for (const [name, info] of Object.entries(fnData.functions)) {
      const cat = info.category;
      if (!grouped[cat]) grouped[cat] = [];
      grouped[cat].push({ name, signature: info.signature, summary: info.summary });
    }
    for (const cat of Object.keys(grouped)) {
      grouped[cat].sort((a, b) => a.name.localeCompare(b.name));
    }
  }

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <TooltipProvider>
      {/* Root: stacked on mobile, side-by-side on desktop */}
      <div className="flex flex-col sm:flex-row w-full sm:h-[560px]">
        {/* ── LEFT COLUMN (desktop) / BOTTOM (mobile): Functions + Variables selector ── */}
        <div
          className={cn(
            "order-2 sm:order-1",
            "sm:w-[260px] sm:flex-shrink-0",
            "border-t sm:border-t-0 sm:border-r border-border",
            "sm:overflow-y-auto",
          )}
        >
          <Tabs defaultValue="functions">
            {/* Tab switcher — sticky on desktop so it stays visible while scrolling the list */}
            <div className="px-3 pt-2 pb-1 sm:sticky sm:top-0 sm:bg-popover sm:z-10 sm:border-b sm:border-border/50">
              <TabsList className="h-8 w-full bg-muted p-0.5">
                <TabsTrigger
                  value="functions"
                  className="flex-1 h-full text-xs px-2 data-[state=active]:bg-background data-[state=active]:shadow-sm"
                >
                  {t("functionsTab")}
                </TabsTrigger>
                <TabsTrigger
                  value="variables"
                  className="flex-1 h-full text-xs px-2 data-[state=active]:bg-background data-[state=active]:shadow-sm"
                >
                  {t("variablesTab")}
                </TabsTrigger>
              </TabsList>
            </div>

            {/* ── Functions tab ── */}
            <TabsContent value="functions" className="mt-0">
              {loadingFns && <p className="text-xs text-muted-foreground px-3 py-2">{t("loading") ?? "Loading…"}</p>}
              {/* Parent column (desktop) or modal (mobile) scrolls — don't nest a scroll here. */}
              <div className="px-2 pb-2 space-y-1">
                {CATEGORY_ORDER.filter((cat) => grouped[cat]?.length).map((cat) => {
                  const isCollapsed = collapsedCategories.has(cat);
                  const fns = grouped[cat] ?? [];
                  const meta = CATEGORY_META[cat];
                  const IconComp = meta?.icon;
                  return (
                    <div key={cat} className={cn("overflow-hidden border-l-2", meta?.border ?? "border-border/0")}>
                      <button
                        type="button"
                        onClick={() => toggleCategory(cat)}
                        className={cn(
                          "flex items-center justify-between w-full px-2 py-1.5 text-[11px] font-semibold transition-colors",
                          "bg-muted/40 hover:bg-muted/70",
                          meta?.text ?? "text-muted-foreground",
                        )}
                      >
                        <span className="flex items-center gap-1.5">
                          {IconComp && <IconComp className="w-3 h-3" />}
                          {categoryLabels[cat] ?? cat}
                        </span>
                        {isCollapsed ? (
                          <ChevronRight className="w-3 h-3 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="w-3 h-3 text-muted-foreground" />
                        )}
                      </button>

                      {!isCollapsed && (
                        <div className="py-0.5">
                          {fns.map((fn) => (
                            <Tooltip key={fn.name}>
                              <TooltipTrigger asChild>
                                <button
                                  type="button"
                                  onClick={() => handleFunctionClick(fn.name)}
                                  className="w-full text-left px-3 py-1 text-xs hover:bg-accent hover:text-accent-foreground transition-colors flex items-baseline gap-2 group"
                                >
                                  <span className="font-mono font-semibold flex-shrink-0">{fn.name}</span>
                                  <span className="font-mono text-[10px] text-muted-foreground truncate group-hover:text-accent-foreground/70">
                                    {fn.signature}
                                  </span>
                                </button>
                              </TooltipTrigger>
                              <TooltipContent side="right" className="max-w-[220px]">
                                <p className="font-mono text-xs font-semibold">{fn.signature}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">{fn.summary}</p>
                              </TooltipContent>
                            </Tooltip>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </TabsContent>

            {/* ── Variables tab ── */}
            <TabsContent value="variables" className="mt-0">
              {/* sm:min-w-0 overrides the component's own min-w to fit the column */}
              <VariablePickerContent
                onInsert={handleVariableInsert}
                maxHeight="400px"
                autoFocusSearch={false}
                className="sm:min-w-0"
              />
            </TabsContent>
          </Tabs>
        </div>

        {/* ── RIGHT COLUMN (desktop) / TOP (mobile): Expression editor + action buttons ── */}
        <div className="order-1 sm:order-2 flex flex-col flex-1 min-w-0 sm:overflow-hidden">
          {/* Desktop: flex column fills, editor sizes within. Mobile: parent modal scrolls — no nested scroll. */}
          <div className="px-3 pt-3 pb-2.5 space-y-1.5 sm:flex-1 sm:flex sm:flex-col sm:overflow-hidden">
            <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">
              {t("formulaExpression")}
            </label>

            {/* Editor container — border changes colour with validation state */}
            <div
              className={cn(
                "rounded-md border overflow-hidden sm:flex-1 sm:flex sm:flex-col sm:min-h-0",
                validationState === "invalid" && "border-destructive",
                validationState === "valid" && "border-green-500",
                validationState !== "invalid" && validationState !== "valid" && "border-border",
              )}
            >
              {/* Top chrome: {{= prefix + validation icon */}
              <div
                className={cn(
                  "flex items-center justify-between px-2.5 py-1 border-b sm:flex-shrink-0",
                  "bg-muted/20 select-none",
                  validationState === "invalid" && "border-destructive/40",
                  validationState === "valid" && "border-green-500/40",
                  validationState !== "invalid" && validationState !== "valid" && "border-border",
                )}
              >
                <span className="text-[10px] text-muted-foreground/50 font-mono">{"{{="}</span>
                <span className="flex items-center">
                  {validationState === "valid" && expr.trim() ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
                  ) : validationState === "invalid" ? (
                    <XCircle className="w-3.5 h-3.5 text-destructive" />
                  ) : validationState === "validating" ? (
                    <Loader2 className="w-3.5 h-3.5 text-muted-foreground/50 animate-spin" />
                  ) : null}
                </span>
              </div>

              {/* CodeMirror mounts here */}
              <div ref={editorContainerRef} className="sm:flex-1 sm:min-h-0 sm:overflow-hidden" />

              {/* Bottom chrome: }} */}
              <div
                className={cn(
                  "px-2.5 py-1 border-t bg-muted/20 select-none sm:flex-shrink-0",
                  validationState === "invalid" && "border-destructive/40",
                  validationState === "valid" && "border-green-500/40",
                  validationState !== "invalid" && validationState !== "valid" && "border-border",
                )}
              >
                <span className="text-[10px] text-muted-foreground/50 font-mono">{"}}"}</span>
              </div>
            </div>

            {/* Error messages */}
            {validationState === "invalid" && errors.length > 0 && (
              <ul className="space-y-0.5">
                {errors.map((msg, i) => (
                  <li key={i} className="flex items-start gap-1 text-[10px] text-destructive">
                    <XCircle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                    <span>{msg}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Action buttons — pinned to bottom of right column */}
          <div className="flex-shrink-0 border-t border-border px-3 py-2 flex justify-end gap-2">
            {mode === "edit" && onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="px-3 py-1.5 rounded-md text-xs font-medium transition-colors border border-border hover:bg-muted/50"
              >
                {initialExpr ? t("close") : t("cancel")}
              </button>
            )}
            <button
              type="button"
              onClick={handleConfirm}
              disabled={isConfirmDisabled}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                "bg-primary text-primary-foreground hover:bg-primary/90",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                "flex items-center gap-1.5",
              )}
            >
              {mode === "create" ? t("insert") : t("done")}
              <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-[9px] font-sans opacity-60 bg-primary-foreground/20">
                ⌘↵
              </kbd>
            </button>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
