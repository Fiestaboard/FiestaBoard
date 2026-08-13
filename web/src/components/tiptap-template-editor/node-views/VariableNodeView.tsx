/**
 * React NodeView for Variable nodes
 * Displays {{plugin.field}} as an interactive badge with filters
 */
import { Badge, Text, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@fiestaboard/ui";
import type { ReactNodeViewProps } from "@tiptap/react";
import { NodeViewWrapper } from "@tiptap/react";
import React from "react";

/** Attributes VariableNode declares (see extensions/variable-node.ts). */
interface VariableAttrs {
  pluginId: string;
  field: string;
  filters: Array<{ name: string; arg?: string }>;
  maxLength?: number;
}

export function VariableNodeView({ node }: ReactNodeViewProps) {
  const { pluginId, field, filters, maxLength } = node.attrs as VariableAttrs;

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
        <Badge
          variant="variable"
          className="inline-flex flex-nowrap items-center gap-1 px-1.5 py-0 border-dashed cursor-grab hover:bg-tag-variable/20 active:cursor-grabbing mr-0.5 transition-all duration-150"
        >
          {/* Raw <span>s throughout this Badge: they render inside TipTap's
              contentEditable where sub-xs sizes (text-[10px]/[11px]) and the
              Badge's inherited "variable" tint are pixel/color load-bearing.
              <Text as="span"> would reset color + size, so kept raw for
              correctness (only the portal Tooltip copy below is primitived). */}
          {/* eslint-disable-next-line react/forbid-elements -- span in a colored Badge in TipTap contentEditable; Text would reset the inherited variable tint and sub-xs text-[11px] grid geometry */}
          <span className="font-mono text-[11px] leading-none">
            {pluginId}.{field}
          </span>

          {filters && filters.length > 0 && (
            // eslint-disable-next-line react/forbid-elements -- inline-flex span wrapping filter chips inside the contentEditable Badge; Text would inject block/tone defaults
            <span className="inline-flex items-center gap-0.5">
              {filters.map((filter, idx) => (
                <Tooltip key={idx}>
                  <TooltipTrigger asChild>
                    {/* eslint-disable-next-line react/forbid-elements -- filter chip span in a colored Badge in contentEditable; Text would reset the inherited tint and sub-xs text-[10px] grid geometry */}
                    <span className="inline-flex items-center px-1 rounded text-[10px] bg-tag-variable/20 leading-none">
                      {filter.name}
                      {filter.arg && `:${filter.arg}`}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    <Text>
                      Filter: {filter.name}
                      {filter.arg ? `:${filter.arg}` : ""}
                    </Text>
                  </TooltipContent>
                </Tooltip>
              ))}
            </span>
          )}

          {maxLength && (
            <Tooltip>
              <TooltipTrigger asChild>
                {/* eslint-disable-next-line react/forbid-elements -- hover-reveal max-length span in the contentEditable Badge; Text would reset sub-xs text-[10px] grid geometry and inherited tint */}
                <span className="hidden group-hover:inline text-[10px] leading-none">~{maxLength}</span>
              </TooltipTrigger>
              <TooltipContent>
                <Text>Max length: {maxLength} characters</Text>
              </TooltipContent>
            </Tooltip>
          )}
        </Badge>
      </TooltipProvider>
    </NodeViewWrapper>
  );
}
