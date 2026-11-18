// The docked formula workbench (desktop ≥1024, 04c §C): the left column gets
// the Builder form or "Line N produces"; the right column gets the Code
// editor, the generated code, or the Inspector pane. Lazy-loaded with
// CodeMirror so the page editor's own chunk does not grow.

"use client";

import { Stack } from "@fiestaboard/ui";

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
