/**
 * Template Editor Toolbar - Toolbar for TipTap template editor
 * Provides quick access to variables, colors, formatting, and alignment
 */
"use client";

import { Editor } from '@tiptap/react';
import { useQuery } from '@tanstack/react-query';
import { AlignLeft, AlignCenter, AlignRight, Code2, Palette, Type, WrapText, Undo2, Redo2, Scissors, Copy, ClipboardPaste, Download, Sigma } from 'lucide-react';
import { api } from '@/lib/api';
import { insertTemplateContent } from '../utils/insertion';
import { ToolbarDropdown } from './ToolbarDropdown';
import { VariablePickerContent } from './VariablePickerContent';
import { ColorPickerContent } from './ColorPickerContent';
import { FormattingPickerContent } from './FormattingPickerContent';

import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import type { LineAlignment } from '../TipTapTemplateEditor';
import type { DeviceType } from '@/lib/api';
import { useState, useEffect, useCallback } from 'react';

interface TemplateEditorToolbarProps {
  editor: Editor | null;
  currentAlignment?: LineAlignment;
  currentWrapEnabled?: boolean;
  onAlignmentChange?: (alignment: LineAlignment) => void;
  onWrapToggle?: () => void;
  className?: string;
  deviceType?: DeviceType;
  onSyncFromBoard?: () => void;
  syncFromBoardPending?: boolean;
}

export function TemplateEditorToolbar({
  editor,
  _currentAlignment = 'left',
  currentWrapEnabled = false,
  onAlignmentChange,
  onWrapToggle,
  className,
  deviceType,
  onSyncFromBoard,
  syncFromBoardPending = false,
}: TemplateEditorToolbarProps) {
  const { data: templateVars } = useQuery({
    queryKey: ["template-variables"],
    queryFn: api.getTemplateVariables,
  });

  const handleInsert = (templateString: string) => {
    if (editor) {
      insertTemplateContent(editor, templateString);
    }
  };

  const handleAlignmentClick = (alignment: LineAlignment) => {
    if (onAlignmentChange) {
      onAlignmentChange(alignment);
    }
  };

  // Check if variables are available
  const hasVariables = templateVars?.variables && Object.keys(templateVars.variables).length > 0;
  const hasColors = templateVars?.colors && Object.keys(templateVars.colors).length > 0;
  const hasFormatting = templateVars?.formatting && Object.keys(templateVars.formatting).length > 0;

  // Track undo/redo availability and selection state
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [hasSelection, setHasSelection] = useState(false);
  const [hasClipboardContent, setHasClipboardContent] = useState(false);

  useEffect(() => {
    if (!editor) {
      setCanUndo(false);
      setCanRedo(false);
      setHasSelection(false);
      return;
    }

    const updateEditorState = () => {
      setCanUndo(editor.can().undo());
      setCanRedo(editor.can().redo());
      const { from, to } = editor.state.selection;
      setHasSelection(from !== to);
    };

    // Initial state
    updateEditorState();

    // Update on editor state changes
    editor.on('update', updateEditorState);
    editor.on('selectionUpdate', updateEditorState);

    return () => {
      editor.off('update', updateEditorState);
      editor.off('selectionUpdate', updateEditorState);
    };
  }, [editor]);

  // Track clipboard content availability for paste button
  useEffect(() => {
    const handleClipboardWrite = () => {
      setHasClipboardContent(true);
    };

    const checkClipboard = async () => {
      try {
        const text = await navigator.clipboard.readText();
        setHasClipboardContent(text.length > 0);
      } catch {
        // Can't read clipboard (permission denied or unavailable) — optimistically enable paste
        setHasClipboardContent(true);
      }
    };

    document.addEventListener('copy', handleClipboardWrite);
    document.addEventListener('cut', handleClipboardWrite);
    window.addEventListener('focus', checkClipboard);
    checkClipboard();

    return () => {
      document.removeEventListener('copy', handleClipboardWrite);
      document.removeEventListener('cut', handleClipboardWrite);
      window.removeEventListener('focus', checkClipboard);
    };
  }, []);

  const handleUndo = () => {
    if (editor && canUndo) {
      editor.chain().focus().undo().run();
    }
  };

  const handleRedo = () => {
    if (editor && canRedo) {
      editor.chain().focus().redo().run();
    }
  };

  const handleCut = useCallback(() => {
    if (editor && hasSelection) {
      editor.view.focus();
      document.execCommand('cut');
      setHasClipboardContent(true);
    }
  }, [editor, hasSelection]);

  const handleCopy = useCallback(() => {
    if (editor && hasSelection) {
      editor.view.focus();
      document.execCommand('copy');
      setHasClipboardContent(true);
    }
  }, [editor, hasSelection]);

  const handlePaste = useCallback(async () => {
    if (!editor) return;
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        editor.chain().focus().insertContent(text).run();
      }
    } catch {
      // Clipboard read failed — focus editor so user can Ctrl+V
      editor.commands.focus();
    }
  }, [editor]);

  return (
    <TooltipProvider>
      <div
        className={cn(
          "flex items-center gap-1 p-2 border rounded-t-md bg-background",
          "flex-wrap",
          className
        )}
      >
        {/* Undo/Redo Controls */}
        <div className="flex items-center gap-0.5 rounded-md border border-border overflow-hidden bg-background">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={handleUndo}
                disabled={!canUndo}
                className={cn(
                  "px-2 py-1.5 transition-colors",
                  canUndo
                    ? "hover:bg-muted/50"
                    : "opacity-60 cursor-not-allowed",
                  "border-r border-border"
                )}
                aria-label="Undo"
              >
                <Undo2 className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Undo (Ctrl+Z)</p>
            </TooltipContent>
          </Tooltip>
          
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={handleRedo}
                disabled={!canRedo}
                className={cn(
                  "px-2 py-1.5 transition-colors",
                  canRedo
                    ? "hover:bg-muted/50"
                    : "opacity-60 cursor-not-allowed"
                )}
                aria-label="Redo"
              >
                <Redo2 className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Redo (Ctrl+Shift+Z)</p>
            </TooltipContent>
          </Tooltip>
        </div>

        {/* Divider after undo/redo */}
        <div className="h-6 w-px bg-border mx-1" />

        {/* Cut/Copy/Paste Controls */}
        <div className="flex items-center gap-0.5 rounded-md border border-border overflow-hidden bg-background">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={handleCut}
                disabled={!hasSelection}
                className={cn(
                  "px-2 py-1.5 transition-colors",
                  hasSelection
                    ? "hover:bg-muted/50"
                    : "opacity-60 cursor-not-allowed",
                  "border-r border-border"
                )}
                aria-label="Cut"
              >
                <Scissors className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Cut (Ctrl+X)</p>
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={handleCopy}
                disabled={!hasSelection}
                className={cn(
                  "px-2 py-1.5 transition-colors",
                  hasSelection
                    ? "hover:bg-muted/50"
                    : "opacity-60 cursor-not-allowed",
                  "border-r border-border"
                )}
                aria-label="Copy"
              >
                <Copy className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Copy (Ctrl+C)</p>
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={handlePaste}
                disabled={!hasClipboardContent}
                className={cn(
                  "px-2 py-1.5 transition-colors",
                  hasClipboardContent
                    ? "hover:bg-muted/50"
                    : "opacity-60 cursor-not-allowed"
                )}
                aria-label="Paste"
              >
                <ClipboardPaste className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Paste (Ctrl+V)</p>
            </TooltipContent>
          </Tooltip>
        </div>

        {/* Divider after clipboard controls */}
        <div className="h-6 w-px bg-border mx-1" />

        {/* Variables Dropdown */}
        {hasVariables ? (
          <ToolbarDropdown
            label="Variables"
            icon={<Code2 className="w-4 h-4" />}
          >
            {(close) => (
              <VariablePickerContent
                onInsert={(variable) => {
                  handleInsert(variable);
                  close();
                }}
              />
            )}
          </ToolbarDropdown>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                disabled
                className={cn(
                  "flex items-center justify-center p-1.5 rounded-md",
                  "text-muted-foreground cursor-not-allowed opacity-60",
                  "border border-transparent"
                )}
                aria-label="Variables (no variables available)"
              >
                <Code2 className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>
              <p>No template variables available. Configure plugins in Settings.</p>
            </TooltipContent>
          </Tooltip>
        )}

        {/* Colors Dropdown */}
        {hasColors && (
          <ToolbarDropdown
            label="Colors"
            icon={<Palette className="w-4 h-4" />}
          >
            {(close) => (
              <ColorPickerContent 
                onInsert={(color) => {
                  handleInsert(color);
                  close();
                }}
                deviceType={deviceType}
              />
            )}
          </ToolbarDropdown>
        )}

        {/* Formatting Dropdown */}
        {hasFormatting && (
          <ToolbarDropdown
            label="Formatting"
            icon={<Type className="w-4 h-4" />}
          >
            {(close) => (
              <FormattingPickerContent
                formatting={templateVars.formatting}
                onInsert={(formatting) => {
                  handleInsert(formatting);
                  close();
                }}
              />
            )}
          </ToolbarDropdown>
        )}

        {/* Formulas — insert an empty formula node; the pill's panel auto-opens in the editor */}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => {
                editor?.chain().focus().insertContent({
                  type: 'formula',
                  attrs: { expression: '', autoOpen: true },
                }).run();
              }}
              className={cn(
                "flex items-center gap-1 px-2 py-1.5 rounded-md text-sm font-medium",
                "hover:bg-muted/50 transition-colors"
              )}
              aria-label="Insert formula"
            >
              <Sigma className="w-4 h-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent>
            <p>Insert formula</p>
          </TooltipContent>
        </Tooltip>

        {/* Wrap Toggle Button */}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onWrapToggle}
              className={cn(
                "flex items-center justify-center p-1.5 rounded-md",
                "hover:bg-muted/50 transition-colors",
                "border border-transparent",
                currentWrapEnabled && "bg-muted/70 border-border"
              )}
              aria-label="Toggle wrap for current line"
            >
              <WrapText className={cn("w-4 h-4", currentWrapEnabled && "text-primary")} />
            </button>
          </TooltipTrigger>
          <TooltipContent>
            <p>{currentWrapEnabled ? "Disable wrap for this line" : "Enable wrap for this line"}</p>
          </TooltipContent>
        </Tooltip>

        {/* Divider */}
        {(hasVariables || hasColors || hasFormatting) && (
          <div className="h-6 w-px bg-border mx-1" />
        )}

        {/* Alignment Controls */}
        <div className="flex items-center gap-0.5 rounded-md border border-border overflow-hidden bg-background">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => handleAlignmentClick('left')}
                className="px-2 py-1.5 transition-colors hover:bg-muted/50"
                aria-label="Align left"
              >
                <AlignLeft className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Align left</TooltipContent>
          </Tooltip>
          
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => handleAlignmentClick('center')}
                className="px-2 py-1.5 border-x border-border transition-colors hover:bg-muted/50"
                aria-label="Align center"
              >
                <AlignCenter className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Align center</TooltipContent>
          </Tooltip>
          
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={() => handleAlignmentClick('right')}
                className="px-2 py-1.5 transition-colors hover:bg-muted/50"
                aria-label="Align right"
              >
                <AlignRight className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Align right</TooltipContent>
          </Tooltip>
        </div>

        {/* Sync from Board — icon-only button pushed to the far right */}
        {onSyncFromBoard && (
          <>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={onSyncFromBoard}
                  disabled={syncFromBoardPending}
                  className={cn(
                    "flex items-center justify-center p-1.5 rounded-md transition-colors",
                    "hover:bg-muted/50 border border-transparent",
                    syncFromBoardPending && "opacity-60 cursor-not-allowed"
                  )}
                  aria-label="Sync from current board display"
                >
                  <Download className={cn("w-4 h-4", syncFromBoardPending && "animate-pulse")} />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Populate template from what&apos;s currently displayed on the board</p>
              </TooltipContent>
            </Tooltip>
          </>
        )}
      </div>
    </TooltipProvider>
  );
}
