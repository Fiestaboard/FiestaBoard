/**
 * React NodeView for Wrapped Text nodes
 * Displays text that will be wrapped with visual indicator
 */
import React from 'react';
import { NodeViewWrapper } from '@tiptap/react';
import { X, WrapText } from 'lucide-react';
import { cn } from '@/lib/utils';

interface WrappedTextViewProps {
  node: {
    attrs: {
      text: string;
    };
  };
  deleteNode: () => void;
}

export function WrappedTextView({ node, deleteNode }: WrappedTextViewProps) {
  const { text } = node.attrs;

  return (
    <NodeViewWrapper
      as="span"
      className={cn(
        'inline-block align-middle rounded-md px-2 py-0.5 text-xs font-medium cursor-grab',
        'border transition-all duration-150',
        'bg-amber-500/15 border-amber-500/30 text-amber-700 dark:text-amber-300',
        'hover:bg-amber-500/20',
        'active:cursor-grabbing',
        'max-h-[1.2rem] h-auto',
        'mr-0.5', // Small space after the tag
      )}
      data-drag-handle
      style={{
        display: 'inline-block',
        verticalAlign: 'middle',
        whiteSpace: 'nowrap',
      }}
    >
      {/* Wrap icon */}
      <WrapText className="w-3 h-3 inline-block align-middle" />
      
      {/* Wrapped text display */}
      <span className="font-mono text-[11px] inline-block align-middle ml-1">
        {text}
      </span>

      {/* Delete button */}
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          deleteNode();
        }}
        className="rounded-full hover:bg-black/10 dark:hover:bg-white/10 p-0.5 -mr-1 ml-0.5 transition-colors"
        tabIndex={-1}
        aria-label="Remove wrapped text"
      >
        <X className="w-3 h-3" />
      </button>
    </NodeViewWrapper>
  );
}
