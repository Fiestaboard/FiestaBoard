/**
 * Template Editor Toolbar - Toolbar for TipTap template editor
 * Provides quick access to variables, colors, formatting, and alignment
 */
"use client";

import { Box, Flex, Skeleton, Text, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import type { Editor } from "@tiptap/react";
import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  ClipboardPaste,
  Code2,
  Copy,
  Download,
  Eraser,
  House,
  Palette,
  Pencil,
  Redo2,
  Scissors,
  SquareFunction,
  Type,
  Undo2,
  WrapText,
} from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";

import { HomeAssistantEntityPicker } from "@/components/home-assistant-entity-picker";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useTranslations } from "@/i18n/translations";
import type { Code62Glyph, DeviceType } from "@/lib/api";
import { api } from "@/lib/api";
import { AVAILABLE_COLORS, getBoardColor } from "@/lib/board-colors";
import { cn } from "@/lib/utils";

import type { LineAlignment } from "../TipTapTemplateEditor";
import type { DrawBrush } from "../utils/draw-mode";
import { insertTemplateContent } from "../utils/insertion";
import { ColorPickerContent } from "./ColorPickerContent";
import { DrawCharPickerContent } from "./DrawCharPickerContent";
import { FormattingPickerContent } from "./FormattingPickerContent";
import { ToolbarDropdown } from "./ToolbarDropdown";

// Lazy-loaded — pulls in lucide-react's full `icons` barrel (every icon in
// the library, ~1.2 MB) to resolve plugin-provided icon names dynamically.
// Deferring it until the "Variables" dropdown is actually opened keeps that
// cost out of the base TipTap editor chunk (#1575).
const VariablePickerContent = lazy(() =>
  import("./VariablePickerContent").then((m) => ({ default: m.VariablePickerContent })),
);

interface TemplateEditorToolbarProps {
  editor: Editor | null;
  currentAlignment?: LineAlignment;
  currentWrapEnabled?: boolean;
  onAlignmentChange?: (alignment: LineAlignment) => void;
  onWrapToggle?: () => void;
  className?: string;
  deviceType?: DeviceType;
  /** Which flap the target board's code-62 slot carries (issue #1657). */
  code62Glyph?: Code62Glyph;
  onSyncFromBoard?: () => void;
  syncFromBoardPending?: boolean;
  drawMode?: boolean;
  onDrawModeToggle?: () => void;
  drawBrush?: DrawBrush;
  onDrawBrushChange?: (brush: DrawBrush) => void;
}

export function TemplateEditorToolbar({
  editor,
  currentAlignment = "left",
  currentWrapEnabled = false,
  onAlignmentChange,
  onWrapToggle,
  className,
  deviceType,
  code62Glyph,
  onSyncFromBoard,
  syncFromBoardPending = false,
  drawMode = false,
  onDrawModeToggle,
  drawBrush,
  onDrawBrushChange,
}: TemplateEditorToolbarProps) {
  const t = useTranslations("templateEditor");
  const effectiveBrush: DrawBrush = drawBrush ?? { kind: "color", color: "red" };
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
  // The Home Assistant entity picker hits `/home-assistant/entities`, which 503s
  // when the plugin isn't installed/enabled. Only offer it when the plugin has
  // actually contributed template variables.
  const hasHomeAssistant = Boolean(templateVars?.variables?.home_assistant);

  // Track undo/redo availability and selection state
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [hasSelection, setHasSelection] = useState(false);
  // Optimistically enabled: we no longer call `navigator.clipboard.readText()`
  // on mount (it triggers Safari's "Smart Paste" floating affordance near
  // focused buttons). The actual read happens inside `handlePaste`, which
  // is a real user-gesture handler and is gesture-allowed in every browser.
  const [hasClipboardContent, setHasClipboardContent] = useState(true);
  const [homeAssistantPickerOpen, setHomeAssistantPickerOpen] = useState(false);
  const pendingHomeAssistantInsert = useRef<number | null>(null);

  // The entity picker emits its variable *before* the dialog tears itself down:
  // it calls `onSelect` and then, synchronously, `onClose`. Inserting here and
  // now would move the caret into the editor only for the dialog's closing focus
  // restore to yank it straight back to the toolbar button, so let that close
  // land first and do the insert on the next frame.
  const handleHomeAssistantSelect = (variable: string) => {
    if (pendingHomeAssistantInsert.current !== null) {
      cancelAnimationFrame(pendingHomeAssistantInsert.current);
    }
    pendingHomeAssistantInsert.current = requestAnimationFrame(() => {
      pendingHomeAssistantInsert.current = null;
      handleInsert(variable);
    });
  };

  useEffect(
    () => () => {
      if (pendingHomeAssistantInsert.current !== null) {
        cancelAnimationFrame(pendingHomeAssistantInsert.current);
        pendingHomeAssistantInsert.current = null;
      }
    },
    [],
  );

  // Clearing the toolbar when the editor goes away is a render-phase reset,
  // not a setState in the effect body (react-hooks/set-state-in-effect,
  // issue #1568) — so the buttons can never stay enabled for a frame after the
  // editor they act on has been torn down.
  if (useDepsChanged([editor]) && !editor) {
    setCanUndo(false);
    setCanRedo(false);
    setHasSelection(false);
  }

  useEffect(() => {
    if (!editor) {
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
    editor.on("update", updateEditorState);
    editor.on("selectionUpdate", updateEditorState);

    return () => {
      editor.off("update", updateEditorState);
      editor.off("selectionUpdate", updateEditorState);
    };
  }, [editor]);

  // Track clipboard content availability for the Paste button.
  //
  // We deliberately do *not* call `navigator.clipboard.readText()` here:
  // doing so on mount or on `window.focus` is the trigger that makes
  // Safari attach its "Smart Paste" floating affordance to whichever
  // button receives focus next (Rich toggle, AI toggle, etc.) — see
  // /Users/jeffrey/.claude/plans/can-we-update-the-inherited-turtle.md
  // for the analysis. The Paste button is optimistically enabled by
  // default; the only place we actually read the clipboard is inside
  // `handlePaste`, which runs from a real user gesture and so doesn't
  // trip Safari's clipboard-aware-page heuristic.
  useEffect(() => {
    const handleClipboardWrite = () => {
      setHasClipboardContent(true);
    };

    const _checkClipboard = async () => {
      try {
        if (!navigator.clipboard?.readText) {
          setHasClipboardContent(false);
          return;
        }

        if (navigator.permissions?.query) {
          try {
            const permissionStatus = await navigator.permissions.query({
              name: "clipboard-read" as PermissionName,
            });
            if (permissionStatus.state === "denied") {
              setHasClipboardContent(false);
              return;
            }
          } catch {
            // Permission API may be unsupported for clipboard-read in some browsers.
          }
        }

        const text = await navigator.clipboard.readText();
        setHasClipboardContent(text.length > 0);
      } catch {
        // Can't read clipboard (permission denied or unavailable) — keep paste disabled
        setHasClipboardContent(false);
      }
    };

    document.addEventListener("copy", handleClipboardWrite);
    document.addEventListener("cut", handleClipboardWrite);
    return () => {
      document.removeEventListener("copy", handleClipboardWrite);
      document.removeEventListener("cut", handleClipboardWrite);
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

  const handleCut = useCallback(async () => {
    if (editor && hasSelection) {
      editor.view.focus();
      const { from, to } = editor.state.selection;
      const selectedText = editor.state.doc.textBetween(from, to, "\n");

      try {
        await navigator.clipboard.writeText(selectedText);
        editor.chain().focus().deleteSelection().run();
      } catch {
        // Fallback for environments where Clipboard API write is unavailable/denied
        document.execCommand("cut");
      }

      setHasClipboardContent(true);
    }
  }, [editor, hasSelection]);

  const handleCopy = useCallback(async () => {
    if (editor && hasSelection) {
      editor.view.focus();
      const { from, to } = editor.state.selection;
      const selectedText = editor.state.doc.textBetween(from, to, "\n");

      try {
        await navigator.clipboard.writeText(selectedText);
      } catch {
        // Fallback for environments where Clipboard API write is unavailable/denied
        document.execCommand("copy");
      }

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
    // `skipDelayDuration={0}` prevents tooltip-flash when clicking
    // adjacent buttons (e.g. the editor card's AI toggle) shifts the
    // layout and the cursor briefly hovers a different button.
    <TooltipProvider skipDelayDuration={0}>
      <Flex align="center" gap="1" wrap className={cn("p-2 border rounded-t-md bg-background", className)}>
        {/* Draw Mode Toggle */}
        {onDrawModeToggle && (
          <>
            <Flex align="center" gap="0.5" className="rounded-md border border-border overflow-hidden bg-background">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={onDrawModeToggle}
                    data-testid="draw-mode-toggle"
                    aria-pressed={drawMode}
                    className={cn(
                      "px-2 py-1.5 transition-colors",
                      drawMode ? "bg-primary text-primary-foreground" : "hover:bg-muted/50",
                    )}
                    aria-label={drawMode ? t("drawModeActive") : t("drawMode")}
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <Text>{drawMode ? t("drawModeActive") : t("drawMode")}</Text>
                </TooltipContent>
              </Tooltip>
            </Flex>

            {/* Divider after draw toggle */}
            <Box className="h-6 w-px bg-border mx-1" />
          </>
        )}

        {/* Undo/Redo Controls */}
        <Flex align="center" gap="0.5" className="rounded-md border border-border overflow-hidden bg-background">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={handleUndo}
                disabled={!canUndo}
                className={cn(
                  "px-2 py-1.5 transition-colors",
                  canUndo ? "hover:bg-muted/50" : "opacity-60 cursor-not-allowed",
                  "border-r border-border",
                )}
                aria-label={t("undoAriaLabel")}
              >
                <Undo2 className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>
              <Text>{t("undo")}</Text>
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
                  canRedo ? "hover:bg-muted/50" : "opacity-60 cursor-not-allowed",
                )}
                aria-label={t("redoAriaLabel")}
              >
                <Redo2 className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent>
              <Text>{t("redo")}</Text>
            </TooltipContent>
          </Tooltip>
        </Flex>

        {/* Divider after undo/redo */}
        <Box className="h-6 w-px bg-border mx-1" />

        {/* Drawing controls — in draw mode the toolbar transforms: all
            content-editing controls are hidden and replaced by inline color
            swatches, an eraser, and a stamp-character dropdown. */}
        {drawMode && (
          <>
            <Flex align="center" gap="0.5">
              {AVAILABLE_COLORS.map((name) => {
                const selected = effectiveBrush.kind === "color" && effectiveBrush.color === name;
                return (
                  <Tooltip key={name}>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        data-testid={`draw-color-${name}`}
                        aria-pressed={selected}
                        aria-label={t(`drawColors.${name}`)}
                        onClick={() => onDrawBrushChange?.({ kind: "color", color: name })}
                        className={cn(
                          "flex items-center justify-center p-1.5 rounded-md transition-colors",
                          "border border-transparent",
                          selected ? "ring-2 ring-primary" : "hover:bg-muted/50",
                        )}
                      >
                        <Text
                          as="span"
                          className="block h-4 w-4 rounded border border-border/50"
                          style={{ backgroundColor: getBoardColor(name) }}
                        />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>
                      <Text>{t(`drawColors.${name}`)}</Text>
                    </TooltipContent>
                  </Tooltip>
                );
              })}

              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    data-testid="draw-color-eraser"
                    aria-pressed={effectiveBrush.kind === "eraser"}
                    aria-label={t("drawEraser")}
                    onClick={() => onDrawBrushChange?.({ kind: "eraser" })}
                    className={cn(
                      "flex items-center justify-center p-1.5 rounded-md transition-colors",
                      "border border-transparent",
                      effectiveBrush.kind === "eraser" ? "ring-2 ring-primary bg-muted/70" : "hover:bg-muted/50",
                    )}
                  >
                    <Eraser className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <Text>{t("drawEraser")}</Text>
                </TooltipContent>
              </Tooltip>
            </Flex>

            <ToolbarDropdown
              label={t("drawCharacter")}
              data-testid="draw-char-dropdown"
              className={cn(effectiveBrush.kind === "char" && "ring-2 ring-primary")}
              icon={
                effectiveBrush.kind === "char" ? (
                  <Text
                    as="span"
                    size="xs"
                    className="flex h-4 w-4 items-center justify-center rounded border border-border font-mono leading-none"
                  >
                    {effectiveBrush.char}
                  </Text>
                ) : (
                  <Type className="w-4 h-4" />
                )
              }
            >
              {(close) => (
                <DrawCharPickerContent
                  current={effectiveBrush}
                  onSelect={(brush) => {
                    onDrawBrushChange?.(brush);
                    close();
                  }}
                />
              )}
            </ToolbarDropdown>
          </>
        )}

        {!drawMode && (
          <>
            {/* Cut/Copy/Paste Controls */}
            <Flex align="center" gap="0.5" className="rounded-md border border-border overflow-hidden bg-background">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={handleCut}
                    disabled={!hasSelection}
                    className={cn(
                      "px-2 py-1.5 transition-colors",
                      hasSelection ? "hover:bg-muted/50" : "opacity-60 cursor-not-allowed",
                      "border-r border-border",
                    )}
                    aria-label={t("cutAriaLabel")}
                  >
                    <Scissors className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <Text>{t("cut")}</Text>
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
                      hasSelection ? "hover:bg-muted/50" : "opacity-60 cursor-not-allowed",
                      "border-r border-border",
                    )}
                    aria-label={t("copyAriaLabel")}
                  >
                    <Copy className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <Text>{t("copy")}</Text>
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
                      hasClipboardContent ? "hover:bg-muted/50" : "opacity-60 cursor-not-allowed",
                    )}
                    aria-label={t("pasteAriaLabel")}
                  >
                    <ClipboardPaste className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <Text>{t("paste")}</Text>
                </TooltipContent>
              </Tooltip>
            </Flex>

            {/* Divider after clipboard controls */}
            <Box className="h-6 w-px bg-border mx-1" />

            {/* Variables Dropdown */}
            {hasVariables ? (
              <ToolbarDropdown label={t("variables")} icon={<Code2 className="w-4 h-4" />}>
                {(close) => (
                  <Suspense
                    fallback={
                      <Box className="p-3 min-w-[300px]">
                        <Skeleton className="h-4 w-full mb-2" />
                        <Skeleton className="h-4 w-3/4 mb-2" />
                        <Skeleton className="h-4 w-1/2" />
                      </Box>
                    }
                  >
                    <VariablePickerContent
                      onInsert={(variable) => {
                        handleInsert(variable);
                        close();
                      }}
                    />
                  </Suspense>
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
                      "border border-transparent",
                    )}
                    aria-label={t("variablesNoVarsAvailable")}
                  >
                    <Code2 className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <Text>{t("noVariablesAvailable")}</Text>
                </TooltipContent>
              </Tooltip>
            )}

            {/* Home Assistant entity picker.
                Deliberately NOT a `ToolbarDropdown`: the dropdown's
                outside-mousedown and capture-phase Escape handlers fight the
                picker's modal portal. A plain button plus a sibling dialog
                keeps both behaving. */}
            {hasHomeAssistant && (
              <>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      data-testid="home-assistant-entity-button"
                      onClick={() => setHomeAssistantPickerOpen(true)}
                      className={cn(
                        "flex items-center justify-center p-1.5 rounded-md transition-colors",
                        "border border-transparent hover:bg-muted/50",
                      )}
                      aria-label={t("homeAssistantEntities")}
                    >
                      <House className="w-4 h-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <Text>{t("homeAssistantEntities")}</Text>
                  </TooltipContent>
                </Tooltip>

                <HomeAssistantEntityPicker
                  open={homeAssistantPickerOpen}
                  onClose={() => setHomeAssistantPickerOpen(false)}
                  onSelect={handleHomeAssistantSelect}
                />
              </>
            )}

            {/* Colors Dropdown */}
            {hasColors && (
              <ToolbarDropdown label={t("colors")} icon={<Palette className="w-4 h-4" />}>
                {(close) => (
                  <ColorPickerContent
                    onInsert={(color) => {
                      handleInsert(color);
                      close();
                    }}
                    deviceType={deviceType}
                    code62Glyph={code62Glyph}
                  />
                )}
              </ToolbarDropdown>
            )}

            {/* Formatting Dropdown */}
            {hasFormatting && (
              <ToolbarDropdown label={t("formatting")} icon={<Type className="w-4 h-4" />}>
                {(close) => (
                  <FormattingPickerContent
                    formatting={templateVars?.formatting}
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
                    editor
                      ?.chain()
                      .focus()
                      .insertContent({
                        type: "formula",
                        attrs: { expression: "", autoOpen: true },
                      })
                      .run();
                  }}
                  className={cn(
                    "flex items-center gap-1 px-2 py-1.5 rounded-md text-sm font-medium",
                    "hover:bg-muted/50 transition-colors",
                  )}
                  aria-label={t("insertFormula")}
                >
                  <SquareFunction className="w-4 h-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <Text>{t("insertFormula")}</Text>
              </TooltipContent>
            </Tooltip>

            {/* Wrap Toggle Button */}
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={onWrapToggle}
                  className={cn(
                    "flex items-center justify-center p-1.5 rounded-md transition-colors",
                    "border border-transparent",
                    currentWrapEnabled ? "bg-primary text-primary-foreground" : "hover:bg-muted/50",
                  )}
                  aria-label={t("toggleWrap")}
                >
                  <WrapText className="w-4 h-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <Text>{currentWrapEnabled ? t("disableWrap") : t("enableWrap")}</Text>
              </TooltipContent>
            </Tooltip>

            {/* Divider */}
            {(hasVariables || hasColors || hasFormatting) && <Box className="h-6 w-px bg-border mx-1" />}

            {/* Alignment Controls */}
            <Flex align="center" gap="0.5" className="rounded-md border border-border overflow-hidden bg-background">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => handleAlignmentClick("left")}
                    className={cn(
                      "px-2 py-1.5 transition-colors",
                      currentAlignment === "left" ? "bg-primary text-primary-foreground" : "hover:bg-muted/50",
                    )}
                    aria-label={t("alignLeft")}
                  >
                    <AlignLeft className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>{t("alignLeft")}</TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => handleAlignmentClick("center")}
                    className={cn(
                      "px-2 py-1.5 border-x border-border transition-colors",
                      currentAlignment === "center" ? "bg-primary text-primary-foreground" : "hover:bg-muted/50",
                    )}
                    aria-label={t("alignCenter")}
                  >
                    <AlignCenter className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>{t("alignCenter")}</TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => handleAlignmentClick("right")}
                    className={cn(
                      "px-2 py-1.5 transition-colors",
                      currentAlignment === "right" ? "bg-primary text-primary-foreground" : "hover:bg-muted/50",
                    )}
                    aria-label={t("alignRight")}
                  >
                    <AlignRight className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>{t("alignRight")}</TooltipContent>
              </Tooltip>
            </Flex>

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
                        syncFromBoardPending && "opacity-60 cursor-not-allowed",
                      )}
                      aria-label={t("syncFromBoard")}
                    >
                      <Download className={cn("w-4 h-4", syncFromBoardPending && "animate-pulse")} />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <Text>{t("syncFromBoardTooltip")}</Text>
                  </TooltipContent>
                </Tooltip>
              </>
            )}
          </>
        )}
      </Flex>
    </TooltipProvider>
  );
}
