/**
 * React NodeView for FillSpace nodes
 * Displays {{fill_space}} as an expandable ruler with estimated expansion
 */
import React from 'react';
import { NodeViewWrapper } from '@tiptap/react';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

interface FillSpaceNodeViewProps {
  node: {
    attrs: {
      id: string;
      repeatChar?: string;
    };
  };
  deleteNode: () => void;
}

export function FillSpaceNodeView({ node, deleteNode }: FillSpaceNodeViewProps) {
  const { repeatChar } = node.attrs;
  const hasRepeatChar = repeatChar && repeatChar !== ' ';
  
  return (
    <NodeViewWrapper
      as="span"
      data-drag-handle
      style={{
        display: 'inline-flex',
        verticalAlign: 'baseline',
        whiteSpace: 'nowrap',
      }}
    >
      <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant="success"
            className="group inline-flex flex-nowrap items-center px-1.5 py-0 border-dashed cursor-grab hover:bg-emerald-500/25 mr-0.5 transition-all duration-150"
          >
        <span className="font-mono text-[11px] leading-none">
          fill_space{hasRepeatChar && `_repeat:${repeatChar}`}
        </span>
      </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <p>{hasRepeatChar ? `Fill space repeating: ${repeatChar}` : "Fill space - expands to fill remaining line width"}</p>
        </TooltipContent>
      </Tooltip>
      </TooltipProvider>
    </NodeViewWrapper>
  );
}
