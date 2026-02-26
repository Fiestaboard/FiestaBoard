/**
 * TipTap Template Editor
 * Unified rich-text editor for Vestaboard templates.
 * Supports variable line counts (6 for Flagship, 3 for Note) via boardLines prop.
 */
"use client";

import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { cn } from '@/lib/utils';
// No longer using custom paragraph extension
import { VariableNode } from './extensions/variable-node';
import { ColorTileNode } from './extensions/color-tile-node';
import { FillSpaceNode } from './extensions/fill-space-node';
import { SymbolNode } from './extensions/symbol-node';
import { WrappedTextNode } from './extensions/wrapped-text-node';
import { UppercaseText } from './extensions/uppercase-text';
import { LineConstraints } from './extensions/line-constraints';
import { LineNavigation } from './extensions/line-navigation';
import { parseTemplateSimple, serializeTemplateSimple, parseLineContent } from './utils/serialization';
import { BOARD_LINES, BOARD_WIDTH } from './utils/constants';
import { calculateLineLength } from './utils/length-calculator';
import { Slice } from '@tiptap/pm/model';
import { TextSelection } from '@tiptap/pm/state';
import { AlignLeft, AlignCenter, AlignRight } from 'lucide-react';
export type LineAlignment = 'left' | 'center' | 'right';
import { TemplateEditorToolbar } from './components/TemplateEditorToolbar';

/**
 * Serialize a TipTap slice to template string format
 * Used for clipboard operations (copy/paste/cut)
 */
function serializeSliceToTemplate(slice: Slice | null | undefined): string {
  try {
    if (!slice || !slice.content || slice.content.size === 0) {
      return '';
    }
    
    let text = '';
    
    // Iterate over the fragment using ProseMirror's forEach method
    slice.content.forEach((node) => {
      if (!node || !node.type) {
        return;
      }
      
      try {
        if (node.type.name === 'text') {
          text += node.text || '';
        } else if (node.type.name === 'variable') {
          const { pluginId, field, filters } = node.attrs || {};
          const filterStr = filters && filters.length > 0 
            ? filters.map((f: any) => `|${f.name}${f.arg ? ':' + f.arg : ''}`).join('')
            : '';
          text += `{{${pluginId || ''}.${field || ''}${filterStr}}}`;
        } else if (node.type.name === 'colorTile') {
          text += `{{${node.attrs?.color || ''}}}`;
        } else if (node.type.name === 'fillSpace') {
          const repeatChar = node.attrs?.repeatChar;
          if (repeatChar && repeatChar !== ' ') {
            text += `{{fill_space_repeat:${repeatChar}}}`;
          } else {
            text += `{{fill_space}}`;
          }
        } else if (node.type.name === 'symbol') {
          text += `{${node.attrs?.name || ''}}`;
        } else if (node.type.name === 'wrappedText') {
          text += `{{${node.attrs?.text || ''}|wrap}}`;
        } else if (node.type.name === 'hardBreak') {
          text += '\n';
        }
      } catch (error) {
        console.warn('Error serializing node:', error);
      }
    });
    
    return text;
  } catch (error) {
    console.warn('Error in serializeSliceToTemplate:', error);
    return '';
  }
}

interface TipTapTemplateEditorProps {
  value: string; // Template string with lines separated by \n
  onChange: (value: string) => void;
  onFocus?: () => void;
  placeholder?: string;
  className?: string;
  showAlignmentControls?: boolean;
  onLineAlignmentChange?: (lineIndex: number, alignment: LineAlignment) => void;
  lineAlignments?: LineAlignment[]; // Array of alignments per line
  onLineWrapChange?: (lineIndex: number, wrapEnabled: boolean) => void;
  lineWrapEnabled?: boolean[]; // Array of wrap states per line
  showToolbar?: boolean; // Show toolbar at top (default: true)
  boardWidth?: number; // Characters per line (default: 22 for flagship)
  boardLines?: number; // Total lines (default: 6 for flagship)
  onLineCountChange?: (lineCount: number) => void; // Reports current line count for validation
}

/**
 * Single TipTap editor for template lines
 */
export function TipTapTemplateEditor({
  value,
  onChange,
  onFocus,
  placeholder = "Type text or insert variables...",
  className,
  showAlignmentControls = true,
  onLineAlignmentChange,
  lineAlignments,
  onLineWrapChange,
  lineWrapEnabled,
  showToolbar = true,
  boardWidth = BOARD_WIDTH,
  boardLines = BOARD_LINES,
  onLineCountChange,
}: TipTapTemplateEditorProps) {
  // Use device-aware defaults when props not provided
  const effectiveAlignments = lineAlignments || Array.from({ length: boardLines }, () => 'left' as LineAlignment);
  const effectiveWrapEnabled = lineWrapEnabled || Array.from({ length: boardLines }, () => false);
  // Track if we're manually updating wrap to prevent onChange from overwriting state
  const isUpdatingWrap = useRef(false);
  
  // Store editor ref for use in handlers
  const editorRef = useRef<any>(null);
  // Track drag state to handle moves properly
  const dragStateRef = useRef<{ from: number; to: number } | null>(null);
  // Track line count for validation display
  const [editorLineCount, setEditorLineCount] = useState(boardLines);
  
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: false,
        blockquote: false,
        codeBlock: false,
        horizontalRule: false,
        bulletList: false,
        orderedList: false,
        listItem: false,
        code: false,
        bold: false,
        italic: false,
        strike: false,
        history: true,
        document: true,
        text: true,
        paragraph: true, // Use standard paragraphs
        hardBreak: true, // Enable hard breaks (Shift+Enter for line breaks within paragraph)
      }),
      VariableNode,
      ColorTileNode,
      FillSpaceNode,
      SymbolNode,
      WrappedTextNode,
      LineNavigation,
      // UppercaseText, // Disabled - using CSS + serialization instead
      // LineConstraints, // Disabled - handling in handleKeyDown and serialization instead
    ],
    content: parseTemplateSimple(value || '', boardLines),
    editorProps: {
      attributes: {
        class: cn(
          'w-full font-mono text-sm',
          'prose prose-sm max-w-none',
          '[&_.ProseMirror]:outline-none',
          '[&_.ProseMirror]:font-mono',
          '[&_.ProseMirror]:text-sm',
          '[&_.ProseMirror]:resize-none',
          '[&_.ProseMirror]:uppercase', // Visual uppercase display
          '[&_.ProseMirror_p]:my-0 [&_.ProseMirror_p]:leading-tight',
          '[&_.ProseMirror_p]:min-h-[1.5rem]',
          className
        ),
        'data-placeholder': placeholder,
        'role': 'textbox',
        'aria-label': 'Template editor',
        'aria-multiline': 'true',
      },
      handleKeyDown: (view, event) => {
        // Handle undo/redo shortcuts explicitly
        // Undo: Ctrl+Z (Windows/Linux) or Cmd+Z (macOS)
        // Redo: Ctrl+Shift+Z, Ctrl+Y (Windows/Linux) or Cmd+Shift+Z, Cmd+Y (macOS)
        const key = event.key.toLowerCase();
        const isMod = event.ctrlKey || event.metaKey;
        
        if (isMod && key === 'z' && !event.shiftKey) {
          // Undo
          const editorInstance = editorRef.current;
          if (editorInstance?.can().undo()) {
            event.preventDefault();
            editorInstance.chain().focus().undo().run();
            return true;
          }
          // If editor not ready yet, don't prevent default - let browser/TipTap handle it
          return false;
        } else if (isMod && (key === 'y' || (key === 'z' && event.shiftKey))) {
          // Redo (Ctrl+Y or Ctrl+Shift+Z)
          const editorInstance = editorRef.current;
          if (editorInstance?.can().redo()) {
            event.preventDefault();
            editorInstance.chain().focus().redo().run();
            return true;
          }
          // If editor not ready yet, don't prevent default - let browser/TipTap handle it
          return false;
        }
        
        // Comprehensive safety checks - prevent any access if view/state not ready
        if (!view) {
          return false;
        }
        if (!view.state) {
          return false;
        }
        if (!view.state.selection) {
          return false;
        }
        if (!view.state.doc) {
          return false;
        }
        if (!view.state.schema) {
          return false;
        }
        
        try {
          const { state } = view;
          const { selection } = state;
          
          // Additional safety check
          if (!selection) {
            return false;
          }
        
        // Enter is handled by the LineNavigation extension (not here).
        
        // Handle Cut (Ctrl/Cmd + X) - copy to clipboard and delete
        if ((event.ctrlKey || event.metaKey) && event.key === 'x') {
          if (selection && !selection.empty) {
            try {
              // Copy selection to clipboard
              const slice = selection.content();
              if (slice) {
                const text = serializeSliceToTemplate(slice);
                
                // Copy to clipboard
                if (navigator.clipboard && navigator.clipboard.writeText) {
                  navigator.clipboard.writeText(text).catch(() => {
                    // Fallback if clipboard API fails
                  });
                }
              }
            } catch (error) {
              console.warn('Error in cut handler:', error);
            }
            
            // Delete selection (TipTap will handle this automatically)
            return false; // Let TipTap handle the cut
          }
        }
        
        // Handle Copy (Ctrl/Cmd + C) - clipboardTextSerializer handles this automatically
        // We don't need to intercept it, TipTap will use clipboardTextSerializer
        // if ((event.ctrlKey || event.metaKey) && event.key === 'c') {
        //   // Let clipboardTextSerializer handle it
        //   return false;
        // }
        
          // Let all other keys work naturally - no blocking or manual conversion
          // UppercaseText extension will handle lowercase conversion via validation
          // Character limits will be handled via validation in onUpdate
          return false;
        } catch (error) {
          console.warn('Error in handleKeyDown:', error);
          return false;
        }
      },
      handlePaste: (view, event, slice) => {
        // Check if we're pasting a template string (contains {{ or {)
        // If so, parse it and insert as nodes
        try {
          const pastedText = event.clipboardData?.getData('text/plain') || '';
          
          if (pastedText && (pastedText.includes('{{') || pastedText.match(/\{[a-z]+\}/i))) {
            const nodes = parseLineContent(pastedText);
            if (nodes.length > 0 && editorRef.current?.state && editorRef.current?.chain) {
              editorRef.current.chain().focus().insertContent(nodes).run();
              return true; // Handled
            }
          }
        } catch (error) {
          console.warn('Error in handlePaste:', error);
        }
        return false; // Let TipTap handle normally
      },
      transformPastedText: (text) => {
        // Skip transformation for template strings (they'll be handled by handlePaste)
        if (text && (text.includes('{{') || text.match(/\{[a-z]+\}/i))) {
          return text; // Don't transform template strings
        }
        // Convert plain text to uppercase for consistency
        // Final uppercase conversion happens during serialization
        return text.toUpperCase();
      },
      handleDOMEvents: {
        // Handle mousedown on drag handles to select the node before dragging
        mousedown: (view, event) => {
          const target = event.target as HTMLElement;
          // Check if clicking on a drag handle or its children
          const dragHandle = target.closest('[data-drag-handle]');
          if (dragHandle && event.button === 0) {
            // Don't handle if clicking on a button (like delete button)
            if (target.closest('button')) {
              return false;
            }
            
            // Get the position of the drag handle element
            const pos = view.posAtDOM(dragHandle, 0);
            if (pos !== null && pos >= 0) {
              try {
                const $pos = view.state.doc.resolve(pos);
                // Try to find the node - it could be before or after the position
                let node = $pos.nodeAfter;
                let nodePos = $pos.pos;
                
                if (!node || (node.type.name !== 'variable' && 
                             node.type.name !== 'colorTile' && 
                             node.type.name !== 'fillSpace' && 
                             node.type.name !== 'symbol' && 
                             node.type.name !== 'wrappedText')) {
                  // Try the node before
                  node = $pos.nodeBefore;
                  if (node) {
                    nodePos = $pos.pos - node.nodeSize;
                  }
                }
                
                if (node && (node.type.name === 'variable' || 
                             node.type.name === 'colorTile' || 
                             node.type.name === 'fillSpace' || 
                             node.type.name === 'symbol' || 
                             node.type.name === 'wrappedText')) {
                  // Store drag state for handleDrop
                  dragStateRef.current = { from: nodePos, to: nodePos + node.nodeSize };
                  
                  // Let the drag continue naturally
                  return false;
                }
              } catch (error) {
                console.warn('Error selecting node for drag:', error);
              }
            }
          }
          return false;
        },
        // Allow dragstart to proceed - we need it for drop events to fire
        dragstart: (view, event) => {
          // Don't prevent - we need the drag to start for drop to work
          return false;
        },
      },
      handleDrop: (view, event, slice, moved) => {
        // Handle dropping a dragged node
        if (dragStateRef.current) {
          const { from, to } = dragStateRef.current;
          
          // Get drop position
          const dropPos = view.posAtCoords({ left: event.clientX, top: event.clientY });
          
          if (dropPos && dropPos.pos !== null) {
            try {
              const $dropPos = view.state.doc.resolve(dropPos.pos);
              
              // Don't drop on itself
              if (dropPos.pos >= from && dropPos.pos <= to) {
                dragStateRef.current = null;
                return true; // Prevent drop
              }
              
              // Get the node being dragged
              const draggedNode = view.state.doc.nodeAt(from);
              if (!draggedNode) {
                dragStateRef.current = null;
                return false;
              }
              
              // Calculate insert position
              let insertPos = $dropPos.pos;
              
              // If dropping at the start of a node, insert before it
              if ($dropPos.parentOffset === 0 && $dropPos.depth > 0) {
                insertPos = $dropPos.before($dropPos.depth);
              }
              
              // Adjust position if dropping after the dragged content
              if (insertPos > to) {
                insertPos -= (to - from);
              }
              
              // Create transaction to move the node
              const tr = view.state.tr;
              
              // Delete from original position
              tr.delete(from, to);
              
              // Adjust insert position after deletion
              const adjustedInsertPos = insertPos > from ? insertPos - (to - from) : insertPos;
              
              // Ensure we're inserting at a valid position
              if (adjustedInsertPos >= 0 && adjustedInsertPos <= tr.doc.content.size) {
                // Insert the node at the new position
                tr.insert(adjustedInsertPos, draggedNode);
                
                // Set cursor after the moved node
                const cursorPos = adjustedInsertPos + draggedNode.nodeSize;
                if (cursorPos <= tr.doc.content.size) {
                  tr.setSelection(TextSelection.create(tr.doc, cursorPos));
                }
                
                view.dispatch(tr);
                dragStateRef.current = null;
                return true; // Handled
              }
            } catch (error) {
              console.warn('Error handling drop:', error);
            }
          }
          dragStateRef.current = null;
        }
        
        // For other drops, let TipTap handle it
        return false;
      },
      clipboardTextSerializer: (slice) => {
        // Serialize nodes to their template string format for clipboard
        try {
          // Safety check - ensure slice is valid
          if (!slice) {
            return '';
          }
          if (!slice.content) {
            return '';
          }
          return serializeSliceToTemplate(slice);
        } catch (error) {
          console.warn('Error in clipboardTextSerializer:', error);
          return '';
        }
      },
    },
    onSelectionUpdate: ({ editor }) => {
      // Toggle .selected-inline on atom node DOM elements that are inside the
      // current range selection so color tiles etc. get a visible highlight.
      const container = editor.view.dom;
      container.querySelectorAll('.selected-inline').forEach(el => {
        el.classList.remove('selected-inline');
      });
      const { selection } = editor.state;
      if (!selection.empty) {
        editor.state.doc.nodesBetween(selection.from, selection.to, (node, pos) => {
          if (node.isAtom && node.isInline) {
            const domNode = editor.view.nodeDOM(pos);
            if (domNode instanceof HTMLElement) {
              domNode.classList.add('selected-inline');
            }
          }
        });
      }
    },
    onUpdate: ({ editor }) => {
      // Skip onChange if we're manually updating wrap (to prevent state overwrite)
      if (isUpdatingWrap.current) {
        return;
      }
      // Safety check
      if (!editor || !editor.state) {
        return;
      }
      const doc = editor.getJSON();
      const templateString = serializeTemplateSimple(doc, boardLines);
      onChange(templateString);

      const lineCount = templateString.split('\n').length;
      setEditorLineCount(lineCount);
      if (onLineCountChange) {
        onLineCountChange(lineCount);
      }
    },
    onFocus: () => {
      onFocus?.();
    },
  });
  
  // Store editor reference for use in handlers
  useEffect(() => {
    if (editor) {
      editorRef.current = editor;
    }
  }, [editor]);

  // Add DOM-level drop handler to ensure we catch drops
  useEffect(() => {
    if (!editor) return;
    
    const editorElement = editor.view.dom;
    
    const handleDrop = (event: DragEvent) => {
      // Only handle if we have drag state (dragging a custom node)
      if (!dragStateRef.current) {
        return;
      }
      
      event.preventDefault();
      event.stopPropagation();
      
      const { from, to } = dragStateRef.current;
      
      // Get drop position using editor's view
      const dropPos = editor.view.posAtCoords({ left: event.clientX, top: event.clientY });
      
      if (dropPos && dropPos.pos !== null) {
        try {
          const $dropPos = editor.state.doc.resolve(dropPos.pos);
          
          // Don't drop on itself
          if (dropPos.pos >= from && dropPos.pos <= to) {
            dragStateRef.current = null;
            return;
          }
          
          // Get the node being dragged
          const draggedNode = editor.state.doc.nodeAt(from);
          if (!draggedNode) {
            dragStateRef.current = null;
            return;
          }
          
          // Calculate insert position
          let insertPos = $dropPos.pos;
          
          // If dropping at the start of a node, insert before it
          if ($dropPos.parentOffset === 0 && $dropPos.depth > 0) {
            insertPos = $dropPos.before($dropPos.depth);
          }
          
          // Adjust position if dropping after the dragged content
          if (insertPos > to) {
            insertPos -= (to - from);
          }
          
          // Create transaction to move the node
          const tr = editor.state.tr;
          
          // Delete from original position
          tr.delete(from, to);
          
          // Adjust insert position after deletion
          const adjustedInsertPos = insertPos > from ? insertPos - (to - from) : insertPos;
          
          // Ensure we're inserting at a valid position
          if (adjustedInsertPos >= 0 && adjustedInsertPos <= tr.doc.content.size) {
            // Insert the node at the new position
            tr.insert(adjustedInsertPos, draggedNode);
            
            // Set cursor after the moved node
            const cursorPos = adjustedInsertPos + draggedNode.nodeSize;
            if (cursorPos <= tr.doc.content.size) {
              tr.setSelection(TextSelection.create(tr.doc, cursorPos));
            }
            
            editor.view.dispatch(tr);
            dragStateRef.current = null;
          }
        } catch (error) {
          console.warn('Error handling DOM drop:', error);
          dragStateRef.current = null;
        }
      }
    };
    
    const handleDragOver = (event: DragEvent) => {
      // Allow drop by preventing default
      if (dragStateRef.current) {
        event.preventDefault();
        event.dataTransfer!.dropEffect = 'move';
      }
    };
    
    editorElement.addEventListener('drop', handleDrop);
    editorElement.addEventListener('dragover', handleDragOver);
    
    return () => {
      editorElement.removeEventListener('drop', handleDrop);
      editorElement.removeEventListener('dragover', handleDragOver);
    };
  }, [editor]);

  // Update editor content when value changes externally
  useEffect(() => {
    if (editor && editor.state) {
      const currentSerialized = serializeTemplateSimple(editor.getJSON(), boardLines);
      if (value !== currentSerialized) {
        editor.commands.setContent(parseTemplateSimple(value || '', boardLines), false, {
          preserveWhitespace: true,
        });
      }
    }
  }, [value, editor]);

  // No need to enforce paragraph count - we use line breaks now

  // Alignment is now handled at serialization level, not in editor

  // Wrap is now handled at serialization level, not in editor

  // Get current line index from cursor position (counting hardBreaks)
  const getCurrentLineIndex = useCallback((): number | null => {
    try {
      if (!editor || !editor.state || !editor.state.selection) return null;
      const { state } = editor;
      const { selection } = state;
      if (!selection || !selection.$from) return null;
      const { $from } = selection;
    
      // Count hard breaks before cursor to determine line index
      let lineIndex = 0;
      if (state.doc) {
        state.doc.nodesBetween(0, $from.pos, (node) => {
          if (node && node.type && node.type.name === 'hardBreak') {
            lineIndex++;
          }
        });
      }
      
      return lineIndex;
    } catch (error) {
      console.warn('Error in getCurrentLineIndex:', error);
      return null;
    }
  }, [editor]);

  // Handle alignment button clicks
  const handleAlignmentClick = useCallback((alignment: LineAlignment) => {
    if (!editor) return;
    
    const lineIndex = getCurrentLineIndex();
    if (lineIndex === null || lineIndex < 0 || lineIndex >= boardLines) {
      return; // Can't apply alignment if no line is selected
    }

    // Notify parent of alignment change (parent handles state)
    if (onLineAlignmentChange) {
      onLineAlignmentChange(lineIndex, alignment);
    }
  }, [editor, getCurrentLineIndex, onLineAlignmentChange]);

  // Handle wrap toggle
  const handleWrapClick = useCallback(() => {
    if (!editor) return;
    
    const lineIndex = getCurrentLineIndex();
    if (lineIndex === null || lineIndex < 0 || lineIndex >= boardLines) {
      return; // Can't apply wrap if no line is selected
    }

    // Get current wrap state and toggle it
    const currentWrap = effectiveWrapEnabled[lineIndex] || false;
    const newWrap = !currentWrap;
    
    // Notify parent of wrap change (parent handles state)
    if (onLineWrapChange) {
      onLineWrapChange(lineIndex, newWrap);
    }
  }, [editor, getCurrentLineIndex, onLineWrapChange, lineWrapEnabled]);

  // Safely get current line index - use useMemo to prevent calculation during problematic renders
  // MUST be called before any early returns to maintain hook order
  const currentLineIndex = useMemo(() => {
    try {
      // Only try to get line index if editor is fully initialized
      if (!editor) {
        return null;
      }
      if (!editor.state) {
        return null;
      }
      if (!editor.state.selection) {
        return null;
      }
      const { state } = editor;
      const { selection } = state;
      if (!selection || !selection.$from) {
        return null;
      }
      const { $from } = selection;
      
      if (!state.doc) {
        return null;
      }
      
      let lineIndex = 0;
      state.doc.nodesBetween(0, $from.pos, (node) => {
        if (node && node.type && node.type.name === 'hardBreak') {
          lineIndex++;
        }
      });
      return lineIndex;
    } catch (error) {
      console.warn('Error getting current line index:', error);
      return null;
    }
  }, [editor, editor?.state?.selection?.$from?.pos]);
  
  const currentAlignment = currentLineIndex !== null && currentLineIndex >= 0 && currentLineIndex < boardLines
    ? effectiveAlignments[currentLineIndex] || 'left'
    : 'left';

  if (!editor) {
    return (
      <div className={cn('min-h-[9rem] border rounded-md p-2 bg-muted/30', className)}>
        <div className="space-y-1">
          {Array.from({ length: boardLines }).map((_, i) => (
            <div key={i} className="h-6 bg-background/50 rounded" />
          ))}
        </div>
      </div>
    );
  }
  const currentWrapEnabled = currentLineIndex !== null && currentLineIndex >= 0 && currentLineIndex < boardLines
    ? effectiveWrapEnabled[currentLineIndex] || false
    : false;

  const isOverLineLimit = editorLineCount > boardLines;

  return (
    <div className={cn('relative', className)}>
      {/* Toolbar */}
      {showToolbar && (
        <TemplateEditorToolbar
          editor={editor}
          currentAlignment={currentAlignment}
          currentWrapEnabled={currentWrapEnabled}
          onAlignmentChange={(alignment) => {
            handleAlignmentClick(alignment);
          }}
          onWrapToggle={() => {
            handleWrapClick();
          }}
        />
      )}
      
      {/* Editor container - styled like a single textarea */}
      <div className="flex-1">
        <div className={cn(
          "border bg-background relative rounded-md",
          showToolbar ? "rounded-t-none" : "",
          isOverLineLimit && "border-amber-500"
        )} style={{ 
          padding: '0.75rem', 
          minHeight: `${boardLines * 1.5 + 1.5}rem`,
        }}>
          <div className="relative" style={{ minHeight: `${boardLines * 1.5}rem` }}>
            <EditorContent editor={editor} />
          </div>
        </div>

        {/* Line counter */}
        <div className={cn(
          "mt-1 text-xs",
          isOverLineLimit ? "text-amber-600 dark:text-amber-400 font-medium" : "text-muted-foreground"
        )}>
          {editorLineCount} / {boardLines} lines
          {isOverLineLimit && ` — exceeds the ${boardLines}-line board limit`}
        </div>

        {/* Alignment controls - only show if toolbar is hidden */}
        {!showToolbar && showAlignmentControls && (
            <div className="flex items-center gap-2 mt-2">
              <span className="text-xs text-muted-foreground">Alignment:</span>
              <div className="flex rounded-md border overflow-hidden">
                <button
                  type="button"
                  onClick={() => handleAlignmentClick('left')}
                  className={cn(
                    'px-3 py-1.5 text-xs transition-colors',
                    currentAlignment === 'left'
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-muted text-muted-foreground'
                  )}
                  title="Align left"
                >
                  <AlignLeft className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => handleAlignmentClick('center')}
                  className={cn(
                    'px-3 py-1.5 text-xs border-x transition-colors',
                    currentAlignment === 'center'
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'hover:bg-muted text-muted-foreground'
                  )}
                  title="Align center"
                >
                  <AlignCenter className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => handleAlignmentClick('right')}
                  className={cn(
                    'px-3 py-1.5 text-xs transition-colors',
                    currentAlignment === 'right'
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-muted text-muted-foreground'
                  )}
                  title="Align right"
                >
                  <AlignRight className="w-4 h-4" />
                </button>
              </div>
              {currentLineIndex !== null && (
                <span className="text-xs text-muted-foreground">
                  (Line {currentLineIndex + 1})
                </span>
              )}
            </div>
          )}
      </div>

      {/* Placeholder styling */}
      <style jsx global>{`
        /* Ensure ProseMirror container looks like a single textarea */
        .ProseMirror {
          margin: 0;
          padding: 0;
          width: 100%;
          max-width: 100%;
          overflow: visible;
          outline: none;
        }
        
        /* Placeholder for first empty line only - textarea-like */
        .ProseMirror[data-placeholder] > p:first-child:empty::before {
          content: attr(data-placeholder);
          color: hsl(var(--muted-foreground));
          pointer-events: none;
          position: absolute;
        }
        
        .ProseMirror:focus[data-placeholder] > p:first-child:empty::before {
          opacity: 0.5;
        }

        /* Standard paragraph - no wrapping, fixed line height */
        .ProseMirror > p {
          margin: 0;
          padding: 0;
          text-transform: uppercase;
          font-family: 'Courier New', 'Courier', monospace;
          font-size: 0.875rem;
          letter-spacing: 0;
          line-height: 1.5rem;
          white-space: nowrap;
          overflow: visible; /* Let content flow naturally, limit via input handling */
          display: block;
        }
        
        /* Hard breaks create line breaks naturally */
        .ProseMirror br {
          display: block;
          content: '';
          margin: 0;
          padding: 0;
          line-height: 0;
        }
        
        /* Prevent any extra spacing around hard breaks */
        .ProseMirror br::before,
        .ProseMirror br::after {
          content: none;
        }
        
        /* Empty paragraph minimum height */
        .ProseMirror > p:empty {
          min-height: 1.5rem;
        }
        
        /* Cursor styling */
        .ProseMirror {
          caret-color: hsl(var(--primary));
        }
        
        .ProseMirror:focus {
          outline: none;
        }
        
        /* Inline nodes - keep them truly inline, no wrapping */
        .ProseMirror [data-type="variable"],
        .ProseMirror [data-type="color-tile"],
        .ProseMirror [data-type="symbol"],
        .ProseMirror [data-type="fill-space"],
        .ProseMirror [data-type="wrapped-text"] {
          display: inline-block !important;
          vertical-align: middle;
          white-space: nowrap;
        }
        
        /* Node view wrappers - prevent wrapping */
        .ProseMirror [data-node-view-wrapper] {
          display: inline-block !important;
          vertical-align: middle;
          white-space: nowrap;
        }
        
        /* Ensure text nodes also don't wrap */
        .ProseMirror p > span {
          white-space: nowrap;
        }
        
        /* All inline nodes must not exceed line height */
        .ProseMirror [data-type="variable"],
        .ProseMirror [data-type="color-tile"],
        .ProseMirror [data-type="symbol"],
        .ProseMirror [data-type="fill-space"],
        .ProseMirror [data-type="wrapped-text"] {
          max-height: 1.4rem !important;
          height: auto !important;
          line-height: 1.4rem;
          vertical-align: middle;
        }
        
        /* Text should be monospace and equal width - each character is exactly 1ch */
        .ProseMirror {
          font-family: 'Courier New', 'Courier', monospace;
          font-variant-numeric: tabular-nums;
        }
        
        /* Don't transform node views (they handle their own display) */
        .ProseMirror [data-type="variable"],
        .ProseMirror [data-type="color-tile"],
        .ProseMirror [data-type="symbol"],
        .ProseMirror [data-type="fill-space"],
        .ProseMirror [data-type="wrapped-text"] {
          text-transform: none;
        }
        
        /* Enable dragging for nodes with data-drag-handle */
        .ProseMirror [data-drag-handle] {
          cursor: grab;
        }
        
        .ProseMirror [data-drag-handle]:active {
          cursor: grabbing;
        }
        
        /* Ensure no weird spacing around inline nodes */
        .ProseMirror [data-type="variable"]::before,
        .ProseMirror [data-type="variable"]::after,
        .ProseMirror [data-type="color-tile"]::before,
        .ProseMirror [data-type="color-tile"]::after {
          content: none;
        }
        
        /* Selection highlighting for inline atom nodes.
           user-select: all makes the browser include the whole node in
           range selections (shift+arrow, click-drag) so they highlight
           with the native selection color just like regular text. */
        .ProseMirror [data-node-view-wrapper] {
          -webkit-user-select: all;
          user-select: all;
        }
        
        /* Range-selection highlight for inline atom nodes (color tiles,
           variables, symbols, fill-space).  onSelectionUpdate adds this
           class to any atom node DOM element inside the selection range. */
        .ProseMirror .selected-inline {
          outline: 2px solid hsl(var(--primary));
          outline-offset: 1px;
          border-radius: 3px;
        }
      `}</style>
    </div>
  );
}
