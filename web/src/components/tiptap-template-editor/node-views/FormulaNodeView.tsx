/**
 * FormulaNodeView — React NodeView for Formula nodes.
 *
 * Renders as an amber badge pill showing ƒ + truncated expression preview.
 * Clicking opens a centered modal FormulaEditorPanel via a portal into
 * document.body (escapes the ProseMirror container).
 *
 * The modal does NOT close on backdrop click — only on Esc / Done / Cancel.
 */
"use client";

import {
  Badge,
  Box,
  Button,
  Flex,
  FormulaAtom,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Text,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@fiestaboard/ui";
import type { ReactNodeViewProps } from "@tiptap/react";
import { NodeViewWrapper } from "@tiptap/react";
import { SquareFunction } from "lucide-react";
import React, { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { atomValueText } from "@/components/formula-ide/atom-text";
import { useFormulaIdeBridge } from "@/components/formula-ide/formula-ide-context";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useTranslations } from "@/i18n/translations";
import { EDITOR_SHORTCUTS, matchesShortcut } from "@/lib/editor-shortcuts";

/** Long-press before a touch on a chip opens Inspect (07c 307:45424). */
const LONG_PRESS_MS = 500;

// Lazy-loaded — CodeMirror (+ the lucide-react icon barrel pulled in via
// VariablePickerContent's "Variables" tab) is only needed once the formula
// modal is actually opened, and keeping it out of the base TipTap editor
// chunk is what keeps that chunk under the 500 kB warning threshold (#1575).
const FormulaEditorPanel = lazy(() =>
  import("../components/FormulaEditorPanel").then((m) => ({ default: m.FormulaEditorPanel })),
);

/** Attributes FormulaNode declares (see extensions/formula-node.ts). */
interface FormulaAttrs {
  expression: string;
  autoOpen: boolean;
}

export function FormulaNodeView({ node, updateAttributes, deleteNode, editor, getPos }: ReactNodeViewProps) {
  const t = useTranslations("formulaEditor");
  const tIde = useTranslations("formulaIde");
  const { expression, autoOpen } = node.attrs;
  const [open, setOpen] = useState(false);
  // Phones get the Formula sheet over the docked preview (306:38107), not a
  // centred modal that covers the whole editor (BB-B-15).
  const phone = useMediaQuery("(max-width: 639px)");
  // Web 2.10: the page editor's formula IDE, when this editor has one. It
  // supplies H5 value hints, the docked desktop editor and Inspect.
  const ide = useFormulaIdeBridge();
  const hint = ide && expression ? ide.hint(expression) : undefined;
  const longPress = useRef<{ timer: ReturnType<typeof setTimeout> | null; fired: boolean; x: number; y: number }>({
    timer: null,
    fired: false,
    x: 0,
    y: 0,
  });
  // The latest node and IDE for callbacks created at open time.
  const latest = useRef({ node, ide, updateAttributes, deleteNode, editor, getPos });
  useEffect(() => {
    latest.current = { node, ide, updateAttributes, deleteNode, editor, getPos };
  });

  /**
   * After the formula editor closes, the caret goes back into the template
   * right after this chip (or where it was, when the chip was removed), so
   * typing carries on and the phone keyboard stays up (BB-B-15).
   */
  const returnCaret = useCallback(() => {
    // After the closing dialog or sheet has handed focus back.
    setTimeout(() => {
      const { editor: view, getPos: position, node: current } = latest.current;
      if (!view || view.isDestroyed) return;
      const at = typeof position === "function" ? position() : undefined;
      if (typeof at === "number") view.commands.focus(at + current.nodeSize);
      else view.commands.focus();
    }, 0);
  }, []);

  /** Open in the docked desktop editor when there is one; else this chip's dialog. */
  const openEditor = useCallback(() => {
    const { ide: bridge } = latest.current;
    const docked = bridge?.openFormula({
      expression: latest.current.node.attrs.expression,
      apply: (next) => latest.current.updateAttributes({ expression: next }),
      cancel: () => {
        if (latest.current.node.attrs.expression === "") latest.current.deleteNode();
      },
    });
    if (!docked) setOpen(true);
  }, []);

  const inspect = useCallback(() => {
    latest.current.ide?.inspectFormula(latest.current.node.attrs.expression);
  }, []);
  // Capture autoOpen at mount time so the effect doesn't depend on the prop
  // (calling updateAttributes would trigger a ProseMirror transaction that can
  // remount this component, cancelling the RAF before it fires).
  const shouldAutoOpen = useRef(autoOpen);

  const preview =
    expression.length > 0 ? (expression.length > 20 ? expression.slice(0, 20) + "…" : expression) : t("newFormula");

  // Auto-open on mount when freshly inserted via the toolbar.
  useEffect(() => {
    if (!shouldAutoOpen.current) return;
    const rafId = requestAnimationFrame(openEditor);
    return () => cancelAnimationFrame(rafId);
  }, [openEditor]);

  const openPanel = useCallback(
    (e: React.MouseEvent) => {
      // A secondary button opens Inspect through the context menu instead.
      if ("button" in e && typeof e.button === "number" && e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      // The compatibility mousedown after a long-press must not also open the editor.
      if (longPress.current.fired) {
        longPress.current.fired = false;
        return;
      }
      openEditor();
    },
    [openEditor],
  );

  const clearLongPress = () => {
    if (longPress.current.timer) clearTimeout(longPress.current.timer);
    longPress.current.timer = null;
  };
  const inspectHandlers = ide
    ? {
        onPointerDown: (e: React.PointerEvent) => {
          if (e.pointerType === "mouse" || !expression) return;
          clearLongPress();
          longPress.current = {
            fired: false,
            x: e.clientX,
            y: e.clientY,
            timer: setTimeout(() => {
              longPress.current.fired = true;
              inspect();
            }, LONG_PRESS_MS),
          };
        },
        onPointerMove: (e: React.PointerEvent) => {
          if (Math.hypot(e.clientX - longPress.current.x, e.clientY - longPress.current.y) > 10) clearLongPress();
        },
        onPointerUp: clearLongPress,
        onPointerCancel: clearLongPress,
        onPointerLeave: clearLongPress,
        onContextMenu: (e: React.MouseEvent) => {
          if (!expression) return;
          e.preventDefault();
          e.stopPropagation();
          inspect();
        },
      }
    : {};

  const triggerProps = {
    // Use onMouseDown instead of onClick — ProseMirror's drag-handle
    // intercepts mousedown on atom nodes before React's onClick fires.
    onMouseDown: openPanel,
    role: "button",
    tabIndex: 0,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openPanel(e as unknown as React.MouseEvent);
      } else if (ide && expression && (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10"))) {
        e.preventDefault();
        inspect();
      }
    },
    ...inspectHandlers,
  };

  // Close on Escape — delete node if it was never given an expression
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (matchesShortcut(e, EDITOR_SHORTCUTS.closePicker)) {
        e.stopPropagation();
        setOpen(false);
        if (node.attrs.expression === "") deleteNode();
        returnCaret();
      }
    };
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [open, node.attrs.expression, deleteNode, returnCaret]);

  const handleConfirm = (newExpr: string) => {
    updateAttributes({ expression: newExpr });
    setOpen(false);
    returnCaret();
  };

  const handleCancel = () => {
    setOpen(false);
    if (node.attrs.expression === "") deleteNode();
    returnCaret();
  };

  // Inspect is a button in the sheet, not only a 500 ms long-press nothing
  // hints at (307:45424; BB-B-15).
  const inspectFromSheet = () => {
    setOpen(false);
    inspect();
  };

  const panel = (
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <FormulaEditorPanel mode="edit" initialExpr={expression} onConfirm={handleConfirm} onCancel={handleCancel} />
    </Suspense>
  );

  return (
    <NodeViewWrapper
      as="span"
      data-drag-handle
      style={{
        display: "inline-flex",
        verticalAlign: "baseline",
        whiteSpace: "nowrap",
      }}
    >
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            {hint ? (
              // Web 2.10 (04c C1): the chip carries its H5 value, `= 3 of 7 rows`.
              // eslint-disable-next-line react/forbid-elements -- inline button role around the noninteractive kit FormulaAtom inside TipTap contentEditable
              <span
                {...triggerProps}
                data-testid="formula-atom-chip"
                className="mr-0.5 inline-flex cursor-pointer rounded-sm normal-case focus-visible:outline-2 focus-visible:outline-ring"
              >
                <FormulaAtom
                  kind="formula"
                  source={expression}
                  value={atomValueText(hint.value, tIde)}
                  state={hint.state}
                />
              </span>
            ) : (
              <Badge
                variant="formula"
                className="inline-flex flex-nowrap items-center gap-1 px-1.5 py-0 border-dashed normal-case cursor-pointer hover:bg-amber-500/20 mr-0.5 transition-all duration-150 active:scale-95"
                {...triggerProps}
              >
                <SquareFunction className="w-2.5 h-2.5 flex-shrink-0" />
                {/* Raw <span>: colored Badge inside contentEditable; <Text as="span">
                    would reset the inherited pill color and text-[11px] is sub-xs
                    grid geometry. Kept raw for correctness. */}
                {/* eslint-disable-next-line react/forbid-elements -- span inside a colored Badge in TipTap contentEditable; Text as="span" would reset the inherited pill color and text-[11px] is sub-xs grid geometry */}
                <span className="font-mono text-[11px] leading-none">{preview}</span>
              </Badge>
            )}
          </TooltipTrigger>
          <TooltipContent>
            <Text size="xs" className="font-mono">
              {"{{= " + expression + " }}"}
            </Text>
            <Text size="xs" tone="muted" className="mt-0.5">
              {t("clickToEditFormula")}
            </Text>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {phone ? (
        <Sheet
          open={open}
          onOpenChange={(next) => {
            if (!next) handleCancel();
          }}
        >
          <SheetContent
            side="bottom"
            grabber
            scrim={false}
            detents={["half", "full"]}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <SheetHeader>
              <Flex align="center" justify="between" gap="2" className="pr-10">
                <SheetTitle>{t("dialogLabel")}</SheetTitle>
                {ide && expression && (
                  <Button variant="outline" size="touch" onClick={inspectFromSheet}>
                    {tIde("inspect")}
                  </Button>
                )}
              </Flex>
            </SheetHeader>
            {panel}
          </SheetContent>
        </Sheet>
      ) : (
        open &&
        createPortal(
          <Flex
            align="center"
            justify="center"
            className="fixed inset-0 z-[999] p-4"
            onMouseDown={(e) => e.stopPropagation()}
          >
            {/* Backdrop — intentionally has no click handler to prevent accidental close */}
            <Box className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

            {/* Modal panel. A real modal dialog, so assistive tech gets dialog
                semantics and the editor's `?` shortcut list stays out of it. */}
            <Box
              role="dialog"
              aria-modal="true"
              aria-label={t("dialogLabel")}
              className="relative rounded-lg border border-border bg-popover shadow-2xl max-h-[90vh] overflow-y-auto w-full max-w-[min(660px,90vw)]"
            >
              {panel}
            </Box>
          </Flex>,
          document.body,
        )
      )}
    </NodeViewWrapper>
  );
}
