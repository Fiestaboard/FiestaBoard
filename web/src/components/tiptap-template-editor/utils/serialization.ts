/**
 * Template string ↔ TipTap document serialization
 * Handles parsing and serializing template syntax while maintaining compatibility
 */

import { JSONContent } from '@tiptap/react';
import { BOARD_COLORS, SYMBOL_CHARS, FILL_SPACE_VAR, FILL_SPACE_REPEAT_VAR } from './constants';

/**
 * Zero-width space (U+200B) inserted at the start and end of each line so
 * the caret always has a text node to sit in (fixes cursor not showing at
 * line boundaries and cursor "selecting" atom nodes on arrow navigation).
 * Stripped on serialize so it never appears in saved template strings.
 */
const CURSOR_ANCHOR_CHAR = '\u200B';

/**
 * Simplified parser - treats template as single block with line breaks
 */
export function parseTemplateSimple(template: string): JSONContent {
  // Enforce 6 line limit during parsing (validation-based, "chill" UX)
  const lines = template.split('\n').slice(0, 6); // Max 6 lines
  
  // Build a single paragraph with content and hardBreaks between lines
  const content: JSONContent[] = [];
  
  lines.forEach((line, index) => {
    // Leading ZWS so cursor renders at the start of the line
    content.push({ type: 'text', text: CURSOR_ANCHOR_CHAR });

    // Parse line content (plain text, no alignment prefixes to extract)
    if (line) {
      const lineNodes = parseLineContent(line);
      content.push(...lineNodes);
    }
    
    // Trailing ZWS so cursor renders at the end of the line
    content.push({ type: 'text', text: CURSOR_ANCHOR_CHAR });
    
    // Add hard break between lines (except after last line)
    if (index < lines.length - 1) {
      content.push({ type: 'hardBreak' });
    }
  });
  
  // Pad with empty breaks to ensure 6 lines total; each padded line gets ZWS so cursor shows
  const currentLines = lines.length;
  for (let i = currentLines; i < 6; i++) {
    if (content.length > 0 && content[content.length - 1].type !== 'hardBreak') {
      content.push({ type: 'hardBreak' });
    }
    // Leading + trailing ZWS (on empty lines they collapse to one, but keep
    // the pair for consistency with content lines)
    content.push({ type: 'text', text: CURSOR_ANCHOR_CHAR });
    content.push({ type: 'text', text: CURSOR_ANCHOR_CHAR });
    if (i < 5) {
      content.push({ type: 'hardBreak' });
    }
  }
  
  return {
    type: 'doc',
    content: [
      {
        type: 'paragraph',
        content: content.length > 0 ? content : undefined,
      },
    ],
  };
}

/**
 * Simplified serializer - converts back to plain text with \n
 */
export function serializeTemplateSimple(doc: JSONContent): string {
  if (!doc.content || doc.content.length === 0) {
    return '\n\n\n\n\n'; // 6 empty lines
  }
  
  const lines: string[] = [];
  let currentLine = '';
  
  // Get the first paragraph (should be the only one)
  const paragraph = doc.content[0];
  if (!paragraph || !paragraph.content) {
    return '\n\n\n\n\n';
  }
  
  // Iterate through paragraph content
  for (const node of paragraph.content) {
    if (node.type === 'hardBreak') {
      // Line break - push current line and start new one
      lines.push(currentLine);
      currentLine = '';
    } else {
      // Add node content to current line
      currentLine += serializeNodeContent(node);
    }
  }
  
  // Push final line
  if (currentLine || lines.length < 6) {
    lines.push(currentLine);
  }
  
  // Ensure exactly 6 lines (validation-based enforcement)
  while (lines.length < 6) {
    lines.push('');
  }
  
  // Enforce 6 line limit during serialization (validation-based, "chill" UX)
  return lines.slice(0, 6).join('\n');
}

/**
 * Serialize a single node to string
 */
function serializeNodeContent(node: JSONContent): string {
  switch (node.type) {
    case 'text':
      // Strip end-of-line cursor placeholder and convert to uppercase
      return (node.text || '').replace(/\u200B/g, '').toUpperCase();
    
    case 'variable':
      const filters = node.attrs?.filters || [];
      const filterStr = filters.length > 0 ? filters.map((f: any) => `|${f.name}${f.args ? ':' + f.args.join(',') : ''}`).join('') : '';
      return `{{${node.attrs?.pluginId}.${node.attrs?.field}${filterStr}}}`;
    
    case 'colorTile':
      return `{{${node.attrs?.color}}}`;
    
    case 'fillSpace':
      const repeatChar = node.attrs?.repeatChar;
      if (repeatChar && repeatChar !== ' ') {
        return `{{fill_space_repeat:${repeatChar}}}`;
      }
      return `{{fill_space}}`;
    
    case 'symbol':
      return `{${node.attrs?.name}}`;
    
    case 'wrappedText':
      return `{{${node.attrs?.text}|wrap}}`;
    
    default:
      return '';
  }
}

/**
 * Parse a template string into TipTap JSON document
 */
export function parseTemplate(template: string): JSONContent {
  const lines = template.split('\n').slice(0, 6); // Max 6 lines
  
  // Pad to exactly 6 lines
  while (lines.length < 6) {
    lines.push('');
  }

  const content: JSONContent[] = lines.map(line => {
    const { alignment, wrapEnabled, content: lineContent } = extractAlignment(line);
    
    return {
      type: 'templateParagraph',
      attrs: { alignment, wrapEnabled },
      content: lineContent ? parseLineContent(lineContent) : [],
    };
  });

  return {
    type: 'doc',
    content,
  };
}

/**
 * Serialize TipTap document back to template string
 */
export function serializeTemplate(doc: JSONContent): string {
  if (!doc.content || doc.content.length === 0) {
    return '\n\n\n\n\n'; // 6 empty lines
  }

  const lines = doc.content.slice(0, 6).map(node => {
    if (node.type !== 'templateParagraph') {
      return '';
    }

    const alignment = node.attrs?.alignment || 'left';
    const wrapEnabled = node.attrs?.wrapEnabled || false;
    const content = serializeLineContent(node.content || []);
    
    return applyAlignment(alignment, wrapEnabled, content);
  });

  // Ensure exactly 6 lines
  while (lines.length < 6) {
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * Extract alignment and wrap directives from line
 */
function extractAlignment(line: string): { alignment: string; wrapEnabled: boolean; content: string } {
  let remaining = line;
  let alignment = 'left';
  let wrapEnabled = false;
  
  // Extract wrap prefix
  if (remaining.startsWith('{wrap}')) {
    wrapEnabled = true;
    remaining = remaining.slice(6);
  }
  
  // Extract alignment prefix (can come after wrap)
  if (remaining.startsWith('{center}')) {
    alignment = 'center';
    remaining = remaining.slice(8);
  } else if (remaining.startsWith('{right}')) {
    alignment = 'right';
    remaining = remaining.slice(7);
  } else if (remaining.startsWith('{left}')) {
    alignment = 'left';
    remaining = remaining.slice(6);
  }
  
  return { alignment, wrapEnabled, content: remaining };
}

/**
 * Apply alignment and wrap prefixes to content
 */
function applyAlignment(alignment: string, wrapEnabled: boolean, content: string): string {
  const prefixes: string[] = [];
  
  // Add wrap prefix first (preserve even for empty lines)
  if (wrapEnabled) {
    prefixes.push('{wrap}');
  }
  
  // Add alignment prefix (only for non-left alignment)
  switch (alignment) {
    case 'center':
      prefixes.push('{center}');
      break;
    case 'right':
      prefixes.push('{right}');
      break;
    // left is default, no prefix needed
  }
  
  // If no prefixes and no content, return empty string
  // Otherwise return prefixes + content (even if content is empty)
  if (prefixes.length === 0 && !content) {
    return '';
  }
  
  return prefixes.join('') + content;
}

/** Node types that are inline atoms (cursor can't sit inside them). */
const ATOM_NODE_TYPES = new Set(['variable', 'colorTile', 'fillSpace', 'symbol']);

/**
 * Parse line content into TipTap nodes
 * Exported for use in insertion utilities
 */
export function parseLineContent(text: string): JSONContent[] {
  const nodes: JSONContent[] = [];
  let remaining = text;

  while (remaining.length > 0) {
    // Try to match double-bracket tokens {{...}}
    const doubleMatch = remaining.match(/^\{\{([^}]+)\}\}/);
    if (doubleMatch) {
      const content = doubleMatch[1];
      const fullMatch = doubleMatch[0];
      
      // Check if it's a color
      const colorName = content.toLowerCase();
      if (colorName in BOARD_COLORS) {
        nodes.push({
          type: 'colorTile',
          attrs: {
            color: colorName,
            code: BOARD_COLORS[colorName as keyof typeof BOARD_COLORS],
          },
        });
      }
      // Check if it's fill_space
      else if (content.toLowerCase() === FILL_SPACE_VAR) {
        nodes.push({
          type: 'fillSpace',
          attrs: {
            id: Math.random().toString(36).substr(2, 9),
          },
        });
      }
      // Check if it's fill_space_repeat with optional character
      else if (content.toLowerCase().startsWith(FILL_SPACE_REPEAT_VAR)) {
        let repeatChar = ' '; // default
        if (content.includes(':')) {
          const parts = content.split(':');
          if (parts.length > 1 && parts[1]) {
            repeatChar = parts[1];
          }
        }
        nodes.push({
          type: 'fillSpace',
          attrs: {
            id: Math.random().toString(36).substr(2, 9),
            repeatChar,
          },
        });
      }
      // Otherwise it's a variable
      else {
        const { varPath, filters } = parseVariable(content);
        // Keep full path after plugin id (e.g. "parks.0.rides.0.ride_abbr" not just "parks")
        const firstDot = varPath.indexOf('.');
        const pluginId = firstDot === -1 ? varPath : varPath.slice(0, firstDot);
        const field = firstDot === -1 ? '' : varPath.slice(firstDot + 1);

        nodes.push({
          type: 'variable',
          attrs: {
            pluginId: pluginId || '',
            field: field || '',
            filters,
          },
        });
      }
      
      remaining = remaining.slice(fullMatch.length);
      continue;
    }

    // Try to match single-bracket tokens {token}
    const singleMatch = remaining.match(/^\{([a-z]+)\}/i);
    if (singleMatch) {
      const tokenName = singleMatch[1].toLowerCase();
      
      // Check if it's a color (single bracket color syntax)
      if (tokenName in BOARD_COLORS) {
        nodes.push({
          type: 'colorTile',
          attrs: {
            color: tokenName,
            code: BOARD_COLORS[tokenName as keyof typeof BOARD_COLORS],
          },
        });
        remaining = remaining.slice(singleMatch[0].length);
        continue;
      }
      
      // Check if it's a symbol
      if (tokenName in SYMBOL_CHARS) {
        nodes.push({
          type: 'symbol',
          attrs: {
            symbol: tokenName,
            character: SYMBOL_CHARS[tokenName],
          },
        });
        remaining = remaining.slice(singleMatch[0].length);
        continue;
      }
    }

    // Plain text - collect until next special token
    const nextToken = remaining.search(/\{\{|\{[a-z]+\}/i);
    if (nextToken === -1) {
      // Rest is plain text
      if (remaining) {
        nodes.push({
          type: 'text',
          text: remaining,
        });
      }
      break;
    } else if (nextToken > 0) {
      // Text before next token
      nodes.push({
        type: 'text',
        text: remaining.slice(0, nextToken),
      });
      remaining = remaining.slice(nextToken);
    } else {
      // Token is at start but didn't match - treat first char as text
      nodes.push({
        type: 'text',
        text: remaining[0],
      });
      remaining = remaining.slice(1);
    }
  }

  // Post-process: insert ZWS between consecutive atom nodes so the cursor
  // has a text position to render between them (e.g. {{red}}{{blue}}).
  const result: JSONContent[] = [];
  for (const node of nodes) {
    const prev = result[result.length - 1];
    if (prev && ATOM_NODE_TYPES.has(prev.type!) && ATOM_NODE_TYPES.has(node.type!)) {
      result.push({ type: 'text', text: '\u200B' });
    }
    result.push(node);
  }
  return result;
}

/**
 * Serialize line content back to string
 */
function serializeLineContent(nodes: JSONContent[]): string {
  return nodes.map(node => {
    switch (node.type) {
      case 'text':
        return node.text || '';
      
      case 'variable':
        const { pluginId, field, filters } = node.attrs || {};
        let varStr = `{{${pluginId}.${field}`;
        if (filters && filters.length > 0) {
          varStr += '|' + filters.map((f: { name: string; arg?: string }) => 
            f.arg ? `${f.name}:${f.arg}` : f.name
          ).join('|');
        }
        varStr += '}}';
        return varStr;
      
      case 'colorTile':
        // Use double bracket syntax for colors to match user input: {{red}}
        return `{{${node.attrs?.color || 'red'}}}`;
      
      case 'fillSpace':
        // Check if it has repeatChar attribute (fill_space_repeat)
        if (node.attrs?.repeatChar) {
          return `{{${FILL_SPACE_REPEAT_VAR}:${node.attrs.repeatChar}}}`;
        }
        return `{{${FILL_SPACE_VAR}}}`;
      
      case 'symbol':
        return `{${node.attrs?.symbol || 'sun'}}`;
      
      case 'wrappedText':
        // Serialize wrapped text as plain text (wrap is handled at render time)
        return node.attrs?.text || '';
      
      default:
        return '';
    }
  }).join('');
}

/**
 * Parse variable expression with filters
 */
function parseVariable(expr: string): { varPath: string; filters: Array<{ name: string; arg?: string }> } {
  const parts = expr.split('|');
  const varPath = parts[0].trim();
  const filters = parts.slice(1).map(f => {
    const colonIndex = f.indexOf(':');
    if (colonIndex === -1) {
      return { name: f.trim() };
    }
    return {
      name: f.slice(0, colonIndex).trim(),
      arg: f.slice(colonIndex + 1).trim(),
    };
  });
  
  return { varPath, filters };
}
