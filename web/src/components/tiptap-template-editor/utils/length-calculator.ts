/**
 * Character counting logic for FiestaBoard
 * Must match backend logic in src/templates/engine.py
 */

import { JSONContent } from '@tiptap/react';
import { BOARD_WIDTH } from './constants';

/**
 * Calculate the rendered length of a line in characters/tiles
 * Matches backend _count_tiles() logic
 */
export function calculateLineLength(lineContent: JSONContent[]): number {
  if (!lineContent || lineContent.length === 0) {
    return 0;
  }

  let tileCount = 0;

  for (const node of lineContent) {
    switch (node.type) {
      case 'text':
        // Regular text counts as actual length (exclude end-of-line cursor placeholder)
        tileCount += (node.text || '').replace(/\u200B/g, '').length;
        break;

      case 'variable':
        // Variables count as maxLength
        tileCount += node.attrs?.maxLength || 10;
        break;

      case 'colorTile':
        // Color tiles count as 1 character
        tileCount += 1;
        break;

      case 'fillSpace':
        // fill_space is calculated dynamically, counts as 0 here
        tileCount += 0;
        break;

      case 'formula':
        // Formula result length is dynamic; use a conservative estimate
        tileCount += node.attrs?.estimatedLength ?? 10;
        break;

      default:
        break;
    }
  }

  return tileCount;
}

/**
 * Check if a line will overflow the board width
 */
export function willOverflow(lineContent: JSONContent[]): boolean {
  const length = calculateLineLength(lineContent);
  return length > BOARD_WIDTH;
}

/**
 * Get overflow amount (0 if no overflow)
 */
export function getOverflowAmount(lineContent: JSONContent[]): number {
  const length = calculateLineLength(lineContent);
  return Math.max(0, length - BOARD_WIDTH);
}

