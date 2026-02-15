/**
 * React NodeView for FillSpace nodes
 * Displays {{fill_space}} as an expandable ruler with estimated expansion
 */
import React from 'react';
import { NodeViewWrapper } from '@tiptap/react';
import { cn } from '@/lib/utils';

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
      className={cn(
        'group inline-flex flex-nowrap items-center rounded-full px-1.5 py-0 text-xs font-medium cursor-grab',
        'border border-dashed transition-all duration-150',
        'bg-emerald-500/15 border-emerald-500/40 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/25',
        'mr-0.5', // Small space after the tag
      )}
      data-drag-handle
      title={hasRepeatChar ? `Fill space repeating: ${repeatChar}` : "Fill space - expands to fill remaining line width"}
      style={{
        display: 'inline-flex',
        verticalAlign: 'baseline',
        whiteSpace: 'nowrap',
      }}
    >
      <span className="font-mono text-[11px] leading-none">
        fill_space{hasRepeatChar && `_repeat:${repeatChar}`}
      </span>
    </NodeViewWrapper>
  );
}
