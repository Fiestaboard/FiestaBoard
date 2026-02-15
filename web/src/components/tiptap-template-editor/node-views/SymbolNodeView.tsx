/**
 * React NodeView for Symbol nodes
 * Displays {sun}, {cloud}, etc. as actual FiestaBoard characters
 */
import React from 'react';
import { NodeViewWrapper } from '@tiptap/react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SymbolNodeViewProps {
  node: {
    attrs: {
      name: string;
      character: string;
    };
  };
  deleteNode: () => void;
}

export function SymbolNodeView({ node, deleteNode }: SymbolNodeViewProps) {
  const { name, character } = node.attrs;

  return (
    <NodeViewWrapper
      as="span"
      className={cn(
        'group inline-block align-middle rounded px-1 py-0.5 text-xs font-mono cursor-grab',
        'bg-amber-500/15 border border-amber-500/30 text-amber-700 dark:text-amber-300',
        'hover:bg-amber-500/20',
        'transition-all duration-150',
        'active:cursor-grabbing',
        'max-h-[1.2rem] h-auto',
      )}
      data-drag-handle
      title={`Symbol: ${name} → "${character}"`}
      style={{
        display: 'inline-block',
        verticalAlign: 'middle',
        whiteSpace: 'nowrap',
      }}
    >
      <span className="font-mono text-[11px]">
        [{character}] {name}
      </span>

      {/* Delete button on hover */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          deleteNode();
        }}
        className={cn(
          'ml-1 inline-flex items-center justify-center',
          'w-3 h-3 rounded-full',
          'bg-amber-600/80 text-white',
          'hover:bg-amber-700',
          'opacity-0 group-hover:opacity-100',
          'transition-opacity',
        )}
        aria-label="Remove symbol"
      >
        <X className="w-2 h-2" />
      </button>
    </NodeViewWrapper>
  );
}
