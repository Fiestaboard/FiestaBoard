// The formula workbench (04c §C). Docked on desktop ≥1024: the left column gets
// the Builder form or "Line N produces"; the right column gets the Code
// editor, the generated code, or the Inspector pane. From 640 to 1023 the same
// Code / Builder editor sits in a bottom sheet (W-5). Lazy-loaded with
// CodeMirror so the page editor's own chunk does not grow.

"use client";

import { Sheet, SheetContent, SheetHeader, SheetTitle, Stack } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import { findLine } from "@/lib/formula-ide/hints";

import { FormulaBuilderCard, GeneratedCodeCard } from "./formula-builder-card";
import { FormulaCodeCard } from "./formula-code-card";
import { FormulaInspectorPane } from "./formula-inspector-pane";
import { LineProducesCard } from "./line-produces-card";
import type { WorkbenchProps } from "./workbench-types";

export function FormulaWorkbenchLeft(props: WorkbenchProps) {
  if (props.open?.tab === "builder") return <FormulaBuilderCard {...props} />;
  const line = props.formula ? findLine(props.diagnostics, props.formula.line) : undefined;
  return line ? <LineProducesCard line={line} rendered={props.rendered} /> : null;
}

export function FormulaWorkbenchRight(props: WorkbenchProps) {
  const inspector = props.inspect ? <FormulaInspectorPane {...props} /> : null;
  const editor = props.open ? (
    props.open.tab === "code" ? (
      <FormulaCodeCard key={props.open.key} {...props} />
    ) : (
      <GeneratedCodeCard {...props} />
    )
  ) : null;
  return (
    <Stack gap="3" className="min-w-0">
      {inspector}
      {editor}
    </Stack>
  );
}

/**
 * The same editor below 1024 px (W-5): a bottom sheet with no scrim, so the
 * board above stays in view, holding Code or Builder exactly as docked. It
 * closes on Cancel, Insert/Update, Esc or its own ×, not on a press outside:
 * the docked editor doesn't either, and the opening tap ends outside it.
 */
export function FormulaWorkbenchSheet(props: WorkbenchProps) {
  const t = useTranslations("formulaIde");
  const { open, setOpen } = props;
  if (!open) return null;
  const sheetProps = { ...props, placement: "sheet" as const };
  return (
    <Sheet
      open
      modal={false}
      disablePointerDismissal
      onOpenChange={(next) => {
        if (next) return;
        open.cancel();
        setOpen(null);
      }}
    >
      {/* As tall as the editor, no taller: the board above stays in view. */}
      <SheetContent
        side="bottom"
        grabber
        scrim={false}
        // The code editor focuses itself on mount; the kit's default would move
        // focus to the first tab and drop a tablet's keyboard. The chip hands the
        // caret back to the template itself on close.
        initialFocus={false}
        finalFocus={false}
        // An Esc the editor already used (closing autocomplete) must not also
        // close the sheet: the kit stops a prevented Esc from reaching the
        // document, and Base UI's own popup handler is skipped for it.
        onEscapeKeyDown={(event) => {
          if (event.defaultPrevented) (event as { preventBaseUIHandler?: () => void }).preventBaseUIHandler?.();
        }}
        data-testid="formula-sheet"
      >
        <SheetHeader className="sr-only">
          <SheetTitle>{props.formula ? t("formulaLine", { line: props.formula.line }) : t("formulaNew")}</SheetTitle>
        </SheetHeader>
        {open.tab === "builder" ? (
          <FormulaBuilderCard {...sheetProps} />
        ) : (
          <FormulaCodeCard key={open.key} {...sheetProps} />
        )}
      </SheetContent>
    </Sheet>
  );
}
