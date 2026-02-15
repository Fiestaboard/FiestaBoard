/**
 * React NodeView for Color Tile nodes
 * Displays {{red}}, {{blue}}, etc. as solid colored tiles
 * Can be dragged and dropped, deleted with backspace, and copied/pasted
 */
import React from 'react';
import { NodeViewWrapper } from '@tiptap/react';
import { cn } from '@/lib/utils';
import { FIESTABOARD_COLORS } from '@/lib/board-colors';

interface ColorTileNodeViewProps {
  node: {
    attrs: {
      color: string;
      code: number;
    };
  };
  deleteNode: () => void;
}

export function ColorTileNodeView({ node, deleteNode }: ColorTileNodeViewProps) {
  const { color, code } = node.attrs;
  const colorKey = color.toLowerCase() as keyof typeof FIESTABOARD_COLORS;
  const bgColor = FIESTABOARD_COLORS[colorKey] || FIESTABOARD_COLORS.red;

  // Match board display styling with 3D effect
  const boxShadow = `
    0 2px 4px rgba(0,0,0,0.3),
    inset 0 1px 1px rgba(255,255,255,0.15),
    inset 0 -1px 1px rgba(0,0,0,0.25),
    inset 1px 0 1px rgba(255,255,255,0.1),
    inset -1px 0 1px rgba(0,0,0,0.2)
  `;

  return (
    <NodeViewWrapper
      as="span"
      className={cn(
        'relative rounded-[3px] cursor-grab',
        'transition-all duration-150',
        'hover:scale-105',
        'active:cursor-grabbing active:scale-100',
      )}
      data-drag-handle
      style={{ 
        backgroundColor: bgColor,
        width: '1.5ch',
        height: '1rem',
        maxHeight: '1rem',
        minHeight: '1rem',
        boxShadow,
        display: 'inline-block',
        verticalAlign: 'middle',
        marginLeft: '1px',
        marginRight: '1px',
        whiteSpace: 'nowrap',
      }}
      title={`${color} tile (code ${code}) - drag to move, backspace to delete`}
    >
      {/* Subtle split flip effect - horizontal line in middle */}
      <div className="absolute top-1/2 left-0 right-0 h-[1px] bg-black/10" />
      
      {/* Subtle gradient for curvature */}
      <div 
        className="absolute inset-0 pointer-events-none rounded-[3px]"
        style={{
          background: 'linear-gradient(180deg, rgba(255,255,255,0.15) 0%, transparent 50%, rgba(0,0,0,0.2) 100%)'
        }}
      />
      
      {/* Block character gives the browser selectable text so the native
          selection highlight (blue overlay) is visible on the tile.
          Transparent color keeps it invisible until selected. */}
      <span
        aria-label={`${color} color tile`}
        style={{
          position: 'absolute',
          inset: 0,
          color: 'transparent',
          overflow: 'hidden',
          lineHeight: '1rem',
          fontSize: '1rem',
          pointerEvents: 'none',
        }}
      >{'\u2588'}</span>
    </NodeViewWrapper>
  );
}
