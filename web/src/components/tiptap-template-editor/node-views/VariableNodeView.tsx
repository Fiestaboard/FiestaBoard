/**
 * React NodeView for Variable nodes.
 *
 * Displays {{plugin.field|filter}} as the kit FormulaAtom (kind "variable",
 * Figma 111:30911 "Atom · weather.temperature"): the source as written, a `{}`
 * glyph, and, in the page editor, the value the preview sees ("= 62").
 */
import { FormulaAtom, Text, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@fiestaboard/ui";
import type { ReactNodeViewProps } from "@tiptap/react";
import { NodeViewWrapper } from "@tiptap/react";
import React, { useId } from "react";

import { atomValueText } from "@/components/formula-ide/atom-text";
import { useFormulaIdeBridge } from "@/components/formula-ide/formula-ide-context";
import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

/** Attributes VariableNode declares (see extensions/variable-node.ts). */
interface VariableAttrs {
  pluginId: string;
  field: string;
  filters: Array<{ name: string; arg?: string }>;
  maxLength?: number;
}

export function VariableNodeView({ node }: ReactNodeViewProps) {
  const t = useTranslations("templateEditor");
  const tIde = useTranslations("formulaIde");
  const descriptionId = useId();
  const { pluginId, field, filters, maxLength } = node.attrs as VariableAttrs;
  const path = `${pluginId}.${field}`;
  const filterText = (filters ?? []).map((filter) => `${filter.name}${filter.arg ? `:${filter.arg}` : ""}`);
  const source = [path, ...filterText].join("|");
  const hint = useFormulaIdeBridge()?.variableHint?.(path);

  return (
    <NodeViewWrapper
      as="span"
      data-drag-handle
      style={{
        display: "inline-flex",
        verticalAlign: "baseline",
        whiteSpace: "nowrap",
      }}
    >
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            {/* The template editor surface is uppercase; a chip shows its source as written (BB-FP-10). */}
            {/* eslint-disable-next-line react/forbid-elements -- inline wrapper around the noninteractive kit FormulaAtom inside TipTap contentEditable */}
            <span
              data-testid="variable-atom-chip"
              aria-describedby={descriptionId}
              className="mr-0.5 inline-flex cursor-grab normal-case active:cursor-grabbing"
            >
              <FormulaAtom
                kind="variable"
                source={source}
                value={hint ? atomValueText(hint.value, tIde) : ""}
                state={hint?.state ?? "ok"}
                // Outside the page editor nothing renders a value: no empty segment.
                className={cn(!hint && "[&>[data-slot=formula-atom-value]]:hidden")}
              />
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <Text size="xs" className="font-mono">
              {`{{${source}}}`}
            </Text>
            {filterText.map((filter) => (
              <Text key={filter} size="xs" tone="muted">
                {t("variableFilterTooltip", { filter })}
              </Text>
            ))}
            {maxLength ? (
              <Text size="xs" tone="muted">
                {t("variableMaxLengthTooltip", { maxLength })}
              </Text>
            ) : null}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      {/* eslint-disable-next-line react/forbid-elements -- screen-reader description of the chip inside TipTap contentEditable */}
      <span id={descriptionId} className="sr-only">
        {maxLength ? t("variableMaxLengthTooltip", { maxLength }) : ""}
      </span>
    </NodeViewWrapper>
  );
}
