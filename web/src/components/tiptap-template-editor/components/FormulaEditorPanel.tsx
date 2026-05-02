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

import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CheckCircle2, XCircle, ChevronDown, ChevronRight, Loader2, GitBranch, Hash, Type as TypeIcon, ArrowLeftRight, Palette } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { VariablePickerContent } from "./VariablePickerContent";

// ─── Category metadata ────────────────────────────────────────────────────────

const CATEGORY_LABELS: Record<string, string> = {
  logic: "Logic",
  math: "Math",
  text: "Text",
  convert: "Conversion",
  color: "Color",
};
const CATEGORY_ORDER = ["logic", "math", "text", "convert", "color"];

const CATEGORY_META: Record<string, { icon: LucideIcon; text: string; border: string }> = {
  logic:   { icon: GitBranch,      text: "text-violet-400", border: "border-l-violet-400/60" },
  math:    { icon: Hash,           text: "text-emerald-400", border: "border-l-emerald-400/60" },
  text:    { icon: TypeIcon,       text: "text-sky-400",    border: "border-l-sky-400/60" },
  convert: { icon: ArrowLeftRight, text: "text-amber-400",  border: "border-l-amber-400/60" },
  color:   { icon: Palette,        text: "text-pink-400",   border: "border-l-pink-400/60" },
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

export function FormulaEditorPanel({
  initialExpr = "",
  mode,
  onConfirm,
  onCancel,
}: FormulaEditorPanelProps) {
  const [expr, setExpr] = useState(initialExpr);
  const [validationState, setValidationState] = useState<
    "idle" | "validating" | "valid" | "invalid"
  >(initialExpr ? "validating" : "idle");
  const [errors, setErrors] = useState<string[]>([]);
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());

  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestExprRef = useRef(expr);
  latestExprRef.current = expr;

  // Guards against the race where expr changed after the last validation cycle
  // confirmed valid but before the next debounce fired.
  const lastValidExprRef = useRef<string | null>(null);

  // Tracks cursor position in the expression input for variable insertion.
  const savedCursorPos = useRef<number>(initialExpr.length);

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

  // Auto-focus on mount
  useEffect(() => {
    inputRef.current?.focus();
    // Select all text in edit mode so the user can immediately replace
    if (mode === "edit" && initialExpr) {
      inputRef.current?.select();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Handlers ─────────────────────────────────────────────────────────────

  const handleConfirm = () => {
    const trimmed = expr.trim();
    if (!trimmed || validationState !== "valid" || lastValidExprRef.current !== trimmed) return;
    onConfirm(trimmed);
  };

  // Scaffold a function call into the input at the current cursor
  const handleFunctionClick = (name: string) => {
    const scaffold = `${name}()`;
    setExpr(scaffold);
    requestAnimationFrame(() => {
      const input = inputRef.current;
      if (input) {
        input.focus();
        const pos = scaffold.length - 1; // just before closing paren
        input.setSelectionRange(pos, pos);
        savedCursorPos.current = pos;
      }
    });
  };

  // Insert a variable token (bare, no {{ }}) at the saved cursor position
  const handleVariableInsert = (variable: string) => {
    // Strip {{  }} wrapper if present (VariablePickerContent returns "{{plugin.field}}")
    const token = variable.replace(/^\{\{/, "").replace(/\}\}$/, "");
    const pos = savedCursorPos.current;
    const newExpr = expr.slice(0, pos) + token + expr.slice(pos);
    const newPos = pos + token.length;
    setExpr(newExpr);
    savedCursorPos.current = newPos;
    requestAnimationFrame(() => {
      const input = inputRef.current;
      if (input) {
        input.focus();
        input.setSelectionRange(newPos, newPos);
      }
    });
  };

  const toggleCategory = (cat: string) => {
    setCollapsedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const isConfirmDisabled =
    !expr.trim() ||
    validationState !== "valid" ||
    lastValidExprRef.current !== expr.trim();

  // ─── Group functions by category ─────────────────────────────────────────

  const grouped: Record<
    string,
    Array<{ name: string; signature: string; summary: string }>
  > = {};
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
      <div className="flex flex-col w-[384px]">

        {/* ── Header: expression input + inline validation ── */}
        <div className="px-3 pt-3 pb-2.5 space-y-1.5">
          <label htmlFor="formula-expression" className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">
            Formula expression
          </label>
          <div className="relative">
            <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground/40 font-mono select-none pointer-events-none">
              {"{{="}
            </span>
            <input
              id="formula-expression"
              ref={inputRef}
              type="text"
              value={expr}
              onChange={(e) => {
                setExpr(e.target.value);
                savedCursorPos.current = e.target.selectionStart ?? e.target.value.length;
              }}
              onSelect={(e) => {
                savedCursorPos.current =
                  (e.target as HTMLInputElement).selectionStart ?? expr.length;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleConfirm();
                }
              }}
              placeholder='IF(weather.temperature > 80, "HOT", "")'
              className={cn(
                "w-full pl-[2.75rem] pr-8 py-1.5 text-xs font-mono rounded-md border",
                "bg-background focus:outline-none focus:ring-2 focus:ring-ring",
                validationState === "invalid" &&
                  "border-destructive focus:ring-destructive/50",
                validationState === "valid" &&
                  "border-green-500 focus:ring-green-500/50"
              )}
              aria-label="Formula expression"
              spellCheck={false}
            />
            {/* Inline validation icon — replaces `}}` chrome */}
            <span className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center pointer-events-none">
              {validationState === "valid" && expr.trim() ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
              ) : validationState === "invalid" ? (
                <XCircle className="w-3.5 h-3.5 text-destructive" />
              ) : validationState === "validating" ? (
                <Loader2 className="w-3.5 h-3.5 text-muted-foreground/50 animate-spin" />
              ) : (
                <span className="text-[10px] text-muted-foreground/40 font-mono">{"}}"}</span>
              )}
            </span>
          </div>

          {/* Error messages only — suppress "Expression looks good" copy */}
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

        {/* ── Tabs: Functions | Variables ── */}
        <div className="border-t border-border">
          <Tabs defaultValue="functions">
            <div className="px-3 pt-2 pb-1">
              <TabsList className="h-8 w-full bg-muted p-0.5">
                <TabsTrigger
                  value="functions"
                  className="flex-1 h-full text-xs px-2 data-[state=active]:bg-background data-[state=active]:shadow-sm"
                >
                  Functions
                </TabsTrigger>
                <TabsTrigger
                  value="variables"
                  className="flex-1 h-full text-xs px-2 data-[state=active]:bg-background data-[state=active]:shadow-sm"
                >
                  Variables
                </TabsTrigger>
              </TabsList>
            </div>

            {/* ── Functions tab ── */}
            <TabsContent value="functions" className="mt-0">
              {loadingFns && (
                <p className="text-xs text-muted-foreground px-3 py-2">Loading…</p>
              )}
              <div className="overflow-y-auto max-h-[240px] px-2 pb-2 space-y-1">
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
                          meta?.text ?? "text-muted-foreground"
                        )}
                      >
                        <span className="flex items-center gap-1.5">
                          {IconComp && <IconComp className="w-3 h-3" />}
                          {CATEGORY_LABELS[cat] ?? cat}
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
                                  <span className="font-mono font-semibold flex-shrink-0">
                                    {fn.name}
                                  </span>
                                  <span className="font-mono text-[10px] text-muted-foreground truncate group-hover:text-accent-foreground/70">
                                    {fn.signature}
                                  </span>
                                </button>
                              </TooltipTrigger>
                              <TooltipContent side="right" className="max-w-[220px]">
                                <p className="font-mono text-xs font-semibold">
                                  {fn.signature}
                                </p>
                                <p className="text-xs text-muted-foreground mt-0.5">
                                  {fn.summary}
                                </p>
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
              <VariablePickerContent onInsert={handleVariableInsert} maxHeight="236px" autoFocusSearch={false} />
            </TabsContent>
          </Tabs>
        </div>

        {/* ── Footer: compact right-aligned action buttons ── */}
        <div className="border-t border-border px-3 py-2 flex justify-end gap-2">
          {mode === "edit" && onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="px-3 py-1.5 rounded-md text-xs font-medium transition-colors border border-border hover:bg-muted/50"
            >
              {initialExpr ? "Close" : "Cancel"}
            </button>
          )}
          <button
            type="button"
            onClick={handleConfirm}
            disabled={isConfirmDisabled}
            className={cn(
              "px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
              "bg-primary text-primary-foreground hover:bg-primary/90",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            {mode === "create" ? "Insert" : "Done"}
          </button>
        </div>

      </div>
    </TooltipProvider>
  );
}
