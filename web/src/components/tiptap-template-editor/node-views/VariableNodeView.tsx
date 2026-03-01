/**
 * React NodeView for Variable nodes
 * Displays {{plugin.field}} as an interactive badge with filters
 */
import React from 'react';
import { NodeViewWrapper } from '@tiptap/react';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

interface VariableNodeViewProps {
  node: {
    attrs: {
      pluginId: string;
      field: string;
      filters: Array<{ name: string; arg?: string }>;
      maxLength?: number;
    };
  };
  deleteNode: () => void;
}

export function VariableNodeView({ node, deleteNode }: VariableNodeViewProps) {
  const { pluginId, field, filters, maxLength } = node.attrs;

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
      <Badge
        variant="variable"
        className="inline-flex flex-nowrap items-center gap-1 px-1.5 py-0 border-dashed cursor-grab hover:bg-tag-variable/20 active:cursor-grabbing mr-0.5 transition-all duration-150"
      >
        <span className="font-mono text-[11px] leading-none">
          {pluginId}.{field}
        </span>

        {filters && filters.length > 0 && (
          <span className="inline-flex items-center gap-0.5">
            {filters.map((filter, idx) => (
              <Tooltip key={idx}>
                <TooltipTrigger asChild>
                  <span className="inline-flex items-center px-1 rounded text-[10px] bg-tag-variable/20 leading-none">
                    {filter.name}
                    {filter.arg && `:${filter.arg}`}
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Filter: {filter.name}{filter.arg ? `:${filter.arg}` : ''}</p>
                </TooltipContent>
              </Tooltip>
            ))}
          </span>
        )}

        {maxLength && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="hidden group-hover:inline text-[10px] leading-none">
                ~{maxLength}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              <p>Max length: {maxLength} characters</p>
            </TooltipContent>
          </Tooltip>
        )}
      </Badge>
      </TooltipProvider>
    </NodeViewWrapper>
  );
}
