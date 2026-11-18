// Code mode (04c 111:30911): the chip's formula pretty-printed in CodeMirror,
// autocomplete over the hub's real built-ins, and each line's value for one
// item in the right margin (H7 trace). Hints never replace the code and hide
// as soon as the text differs from what the hub traced.

"use client";

import { autocompletion, type Completion, type CompletionContext } from "@codemirror/autocomplete";
import { history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { HighlightStyle, StreamLanguage, syntaxHighlighting } from "@codemirror/language";
import { EditorState, RangeSetBuilder, StateEffect, StateField } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, keymap, lineNumbers, WidgetType } from "@codemirror/view";
import { Badge, Box, Button, Card, CardContent, Flex, List, ListItem, Text } from "@fiestaboard/ui";
import { tags } from "@lezer/highlight";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Sigma } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import type { FunctionSignatureEntry } from "@/lib/api/templates";
import { completionContext, matchFunctions } from "@/lib/formula-ide/autocomplete";
import { flattenFormula, iterationCount, lineValueHints, prettyPrint } from "@/lib/formula-ide/pretty";

import { WorkbenchHeader } from "./workbench-header";
import type { WorkbenchProps } from "./workbench-types";

const formulaLanguage = StreamLanguage.define({
  token(stream) {
    if (stream.eatSpace()) return null;
    if (stream.match(/"[^"]*"?/)) return "string";
    if (stream.match(/\d+\.?\d*/)) return "number";
    if (stream.match(/[a-z_][a-z0-9_]*(?::[\w-]+)?(?:\.[a-z0-9_]+)*/)) return "variable";
    if (stream.match(/[A-Z][A-Z0-9_]*/)) return "function";
    if (stream.match(/<>|[<>]=?|[!=]=?|[+\-*/&]/)) return "operator";
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

// Colours are the kit's tag tokens (formula, variable, success), so both themes follow FiestaUI.
const highlighter = HighlightStyle.define([
  { tag: tags.keyword, color: "var(--tag-formula)" },
  { tag: tags.variableName, color: "var(--tag-variable)" },
  { tag: tags.string, color: "var(--tag-success-foreground)" },
  // `--hue-yellow` is the kit's ink-plateau yellow for text; `--warning` is a fill (≈3:1 on light).
  { tag: tags.number, color: "var(--hue-yellow)" },
  { tag: tags.operator, color: "var(--muted-foreground)" },
  { tag: tags.punctuation, color: "var(--muted-foreground)" },
]);

const theme = EditorView.theme({
  "&": { fontFamily: "var(--font-mono-stack)", fontSize: "12px", background: "transparent" },
  ".cm-content": {
    padding: "8px 0",
    paddingRight: "9rem",
    caretColor: "var(--foreground)",
    color: "var(--foreground)",
  },
  ".cm-line": { position: "relative" },
  "&.cm-focused": { outline: "none" },
  ".cm-gutters": { background: "transparent", border: "none", color: "var(--muted-foreground)" },
  ".cm-activeLine": { background: "transparent" },
  // Out of flow, so a hint never changes a line's height (the gutter stays aligned).
  ".cm-value-hint": {
    position: "absolute",
    right: "calc(8px - 9rem)",
    top: "0",
    padding: "0 6px",
    borderRadius: "3px",
    background: "var(--muted)",
    color: "var(--foreground)",
    fontWeight: "500",
    whiteSpace: "pre",
  },
  ".cm-tooltip.cm-tooltip-autocomplete": {
    background: "var(--popover)",
    color: "var(--popover-foreground)",
    border: "1px solid var(--border)",
    borderRadius: "10px",
    overflow: "hidden",
  },
  ".cm-tooltip-autocomplete > ul > li[aria-selected]": {
    background: "var(--color-tint-selected)",
    color: "var(--foreground)",
  },
  ".cm-completionDetail": { float: "right", fontStyle: "normal", color: "var(--muted-foreground)" },
  ".cm-tooltip.cm-completionInfo": {
    background: "var(--popover)",
    color: "var(--popover-foreground)",
    border: "1px solid var(--border)",
    borderRadius: "10px",
    padding: "8px 12px",
    maxWidth: "320px",
  },
});

class HintWidget extends WidgetType {
  constructor(readonly text: string) {
    super();
  }
  eq(other: HintWidget) {
    return other.text === this.text;
  }
  toDOM() {
    const span = document.createElement("span");
    span.className = "cm-value-hint";
    span.textContent = this.text;
    return span;
  }
}

const setHints = StateEffect.define<Array<string | null>>();
const hintField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, tr) {
    let next = value.map(tr.changes);
    for (const effect of tr.effects) {
      if (!effect.is(setHints)) continue;
      const builder = new RangeSetBuilder<Decoration>();
      effect.value.forEach((hint, index) => {
        if (hint === null || index >= tr.state.doc.lines) return;
        const line = tr.state.doc.line(index + 1);
        builder.add(line.to, line.to, Decoration.widget({ widget: new HintWidget(hint), side: 1 }));
      });
      next = builder.finish();
    }
    return next;
  },
  provide: (field) => EditorView.decorations.from(field),
});

function completionSource(
  functions: () => Record<string, FunctionSignatureEntry> | undefined,
  categories: (c: string) => string,
) {
  return (context: CompletionContext) => {
    const text = context.state.doc.toString();
    const match = completionContext(text, context.pos);
    if (!match || (match.word.length < 2 && !context.explicit)) return null;
    const options: Completion[] = matchFunctions(match.word, functions()).map((fn) => ({
      label: `${fn.name}(`,
      detail: categories(fn.category),
      type: "function",
      info: () => {
        const box = document.createElement("div");
        const sig = document.createElement("div");
        sig.style.fontFamily = "var(--font-mono-stack)";
        sig.textContent = fn.signature;
        const summary = document.createElement("div");
        summary.textContent = fn.summary;
        box.append(sig, summary);
        return box;
      },
    }));
    return options.length ? { from: match.from, options, validFor: /^[A-Za-z_][A-Za-z0-9_]*$/ } : null;
  };
}

export function FormulaCodeCard(props: WorkbenchProps) {
  const { open, setOpen, formula, iteration: baseIteration } = props;
  const trace =
    props.trace && formula && props.trace.line === formula.line && props.trace.start === formula.start
      ? props.trace
      : null;
  const t = useTranslations("formulaIde");
  const tEditor = useTranslations("formulaEditor");
  const labelId = useId();
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const original = open?.expression ?? "";
  const printed = useMemo(() => prettyPrint(original), [original]);
  const [text, setText] = useState(() => (open?.draft != null ? prettyPrint(open.draft).text : printed.text));
  const [iteration, setIteration] = useState(baseIteration);
  const [validation, setValidation] = useState<{
    state: "idle" | "validating" | "valid" | "invalid";
    errors: string[];
  }>({
    state: "idle",
    errors: [],
  });

  const { data: fnData } = useQuery({
    queryKey: ["formula-functions"],
    queryFn: api.getFormulaFunctions,
    staleTime: Infinity,
  });
  const functionsRef = useRef(fnData?.functions);
  useEffect(() => {
    functionsRef.current = fnData?.functions;
  }, [fnData]);
  const categoryLabel = useRef((c: string) => c);
  useEffect(() => {
    categoryLabel.current = (c: string) => {
      const key = {
        logic: "categoryLogic",
        math: "categoryMath",
        text: "categoryText",
        convert: "categoryConversion",
        color: "categoryColor",
        array: "categoryArray",
        date: "categoryDate",
      }[c];
      return key ? tEditor(key) : c;
    };
  }, [tEditor]);

  const expression = flattenFormula(text);

  // Validate through the hub (unknown names come back #NAME?), debounced.
  useEffect(() => {
    const body = expression.trim();
    if (!body) return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const result = await api.validateTemplate(`{{= ${body} }}`);
        if (cancelled) return;
        setValidation(
          result.valid
            ? { state: "valid", errors: [] }
            : { state: "invalid", errors: result.errors.map((e) => e.message.replace(/^Formula\s+/, "")) },
        );
      } catch {
        if (!cancelled) setValidation({ state: "idle", errors: [] });
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [expression]);

  useEffect(() => {
    if (!host.current) return;
    const editor = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: text,
        extensions: [
          lineNumbers(),
          formulaLanguage,
          syntaxHighlighting(highlighter),
          theme,
          hintField,
          history(),
          EditorView.contentAttributes.of({ "aria-labelledby": labelId }),
          autocompletion({
            override: [
              completionSource(
                () => functionsRef.current,
                (c) => categoryLabel.current(c),
              ),
            ],
            icons: false,
          }),
          keymap.of([...historyKeymap, indentWithTab]),
          EditorView.updateListener.of((update) => {
            if (!update.docChanged) return;
            const next = update.state.doc.toString();
            setText(next);
            setValidation((v) => ({ ...v, state: "validating" }));
            setOpen((current) => (current ? { ...current, draft: flattenFormula(next) } : current));
          }),
        ],
      }),
    });
    view.current = editor;
    editor.focus();
    return () => {
      editor.destroy();
      view.current = null;
    };
    // The editor is created once per opened chip (the card is keyed by it).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Margin values only while the text is exactly what the hub traced.
  const unedited = text === printed.text;
  const total = trace && unedited ? iterationCount(trace.events) : 1;
  const hints = useMemo(
    () => (trace && unedited ? lineValueHints(trace.events, printed.lines, iteration) : []),
    [trace, unedited, printed, iteration],
  );
  useEffect(() => {
    view.current?.dispatch({ effects: setHints.of(hints) });
  }, [hints]);

  if (!open) return null;
  const canApply = expression.trim().length > 0 && validation.state === "valid";
  const status =
    validation.state === "valid" ? (
      <Badge variant="success">{t("valid")}</Badge>
    ) : validation.state === "invalid" ? (
      <Badge variant="destructive">{t("invalid")}</Badge>
    ) : null;

  return (
    <Card data-testid="formula-code-card" className="gap-2 border-ring py-3">
      <CardContent className="px-4">
        <WorkbenchHeader line={formula?.line ?? null} tab="code" setOpen={setOpen} status={status} />
        <Text id={labelId} className="sr-only">
          {t("codeLabel")}
        </Text>
        <Box
          ref={host}
          className="mt-2 max-h-72 overflow-auto rounded-lg border bg-background"
          data-testid="formula-code"
        />
        {validation.state === "invalid" && validation.errors.length > 0 && (
          <List className="mt-1">
            {validation.errors.map((message) => (
              <ListItem key={message}>
                <Text size="xs" tone="destructive">
                  {message}
                </Text>
              </ListItem>
            ))}
          </List>
        )}
        <Flex align="center" justify="between" gap="2" wrap className="mt-3">
          {total > 1 ? (
            <Flex align="center" gap="1" data-testid="item-stepper">
              <Text size="xs" tone="muted" className="font-mono">
                {t("valuesForItem")}
              </Text>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={t("previousItem")}
                disabled={iteration === 0}
                onClick={() => setIteration((i) => Math.max(i - 1, 0))}
              >
                <ChevronLeft aria-hidden />
              </Button>
              <Text size="xs" className="font-mono" aria-live="polite">
                {t("itemOf", { item: iteration + 1, total })}
              </Text>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={t("nextItem")}
                disabled={iteration >= total - 1}
                onClick={() => setIteration((i) => Math.min(i + 1, total - 1))}
              >
                <ChevronRight aria-hidden />
              </Button>
            </Flex>
          ) : (
            <Text size="xs" tone="muted">
              {unedited ? t("hintsNote") : t("hintsStale")}
            </Text>
          )}
          <Flex gap="2">
            <Button
              variant="ghost"
              onClick={() => {
                open.cancel();
                setOpen(null);
              }}
            >
              {t("cancel")}
            </Button>
            <Button
              disabled={!canApply}
              onClick={() => {
                open.apply(expression.trim());
                setOpen(null);
              }}
            >
              <Sigma aria-hidden />
              {t("updateFormula")}
            </Button>
          </Flex>
        </Flex>
      </CardContent>
    </Card>
  );
}
