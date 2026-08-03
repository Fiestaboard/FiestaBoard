/**
 * React NodeView for FillSpace nodes
 * Displays {{fill_space}} as an expandable ruler with estimated expansion
 */
import { Badge, Text, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@fiestaboard/ui";
import { NodeViewWrapper } from "@tiptap/react";
import React from "react";

interface FillSpaceNodeViewProps {
  node: {
    attrs: {
      id: string;
      repeatChar?: string;
    };
  };
  deleteNode: () => void;
}

export function FillSpaceNodeView({ node, deleteNode: _deleteNode }: FillSpaceNodeViewProps) {
  const { repeatChar } = node.attrs;
  const hasRepeatChar = repeatChar && repeatChar !== " ";

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
            <Badge
              variant="success"
              className="group inline-flex flex-nowrap items-center px-1.5 py-0 border-dashed cursor-grab hover:bg-tag-success/25 mr-0.5 transition-all duration-150"
            >
              {/* Raw <span>: lives inside a colored Badge within TipTap's
                  contentEditable. <Text as="span"> would emit text-foreground,
                  overriding the Badge's inherited success tint, and text-[11px]
                  is sub-xs grid geometry. Kept raw for correctness. */}
              {/* eslint-disable-next-line react/forbid-elements -- span inside a colored Badge in TipTap contentEditable; Text as="span" would override the Badge's inherited tint and text-[11px] is sub-xs grid geometry */}
              <span className="font-mono text-[11px] leading-none">
                fill_space{hasRepeatChar && `_repeat:${repeatChar}`}
              </span>
            </Badge>
          </TooltipTrigger>
          <TooltipContent>
            <Text>
              {hasRepeatChar
                ? `Fill space repeating: ${repeatChar}`
                : "Fill space - expands to fill remaining line width"}
            </Text>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </NodeViewWrapper>
  );
}
