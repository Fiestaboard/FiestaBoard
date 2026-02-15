/**
 * React NodeView for Variable nodes
 * Displays {{plugin.field}} as an interactive badge with filters
 */
import React from 'react';
import { NodeViewWrapper } from '@tiptap/react';
import { cn } from '@/lib/utils';

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
      className={cn(
        'inline-flex flex-nowrap items-center gap-1 rounded-full px-1.5 py-0 text-xs font-medium cursor-grab',
        'border border-dashed transition-all duration-150',
        'bg-indigo-500/15 border-indigo-500/30 text-indigo-700 dark:text-indigo-300',
        'hover:bg-indigo-500/20',
        'active:cursor-grabbing',
        'mr-0.5', // Small space after the tag
      )}
      data-drag-handle
      style={{
        display: 'inline-flex',
        verticalAlign: 'baseline',
        whiteSpace: 'nowrap',
      }}
    >
      {/* Variable display */}
      <span className="font-mono text-[11px] leading-none">
        {pluginId}.{field}
      </span>

      {/* Filters */}
      {filters && filters.length > 0 && (
        <span className="inline-flex items-center gap-0.5">
          {filters.map((filter, idx) => (
            <span
              key={idx}
              className="inline-flex items-center px-1 rounded text-[10px] bg-indigo-500/20 leading-none"
              title={`Filter: ${filter.name}${filter.arg ? `:${filter.arg}` : ''}`}
            >
              {filter.name}
              {filter.arg && `:${filter.arg}`}
            </span>
          ))}
        </span>
      )}

      {/* Max length indicator (on hover) - hidden to not take up space */}
      {maxLength && (
        <span
          className="hidden group-hover:inline text-[10px] opacity-50 leading-none"
          title={`Max length: ${maxLength} characters`}
        >
          ~{maxLength}
        </span>
      )}
    </NodeViewWrapper>
  );
}
