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
  Flex,
  Skeleton,
  Text,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@fiestaboard/ui";
import { NodeViewWrapper } from "@tiptap/react";
import { SquareFunction } from "lucide-react";
import React, { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useTranslations } from "@/i18n/translations";

// Lazy-loaded — CodeMirror (+ the lucide-react icon barrel pulled in via
// VariablePickerContent's "Variables" tab) is only needed once the formula
// modal is actually opened, and keeping it out of the base TipTap editor
// chunk is what keeps that chunk under the 500 kB warning threshold (#1575).
const FormulaEditorPanel = lazy(() =>
  import("../components/FormulaEditorPanel").then((m) => ({ default: m.FormulaEditorPanel })),
);

interface FormulaNodeViewProps {
  node: {
    attrs: {
      expression: string;
      autoOpen: boolean;
    };
  };
  updateAttributes: (attrs: Partial<{ expression: string; autoOpen: boolean }>) => void;
  deleteNode: () => void;
}

export function FormulaNodeView({ node, updateAttributes, deleteNode }: FormulaNodeViewProps) {
  const t = useTranslations("formulaEditor");
  const { expression, autoOpen } = node.attrs;
  const [open, setOpen] = useState(false);
  // Capture autoOpen at mount time so the effect doesn't depend on the prop
  // (calling updateAttributes would trigger a ProseMirror transaction that can
  // remount this component, cancelling the RAF before it fires).
  const shouldAutoOpen = useRef(autoOpen);

  const preview =
    expression.length > 0 ? (expression.length > 20 ? expression.slice(0, 20) + "…" : expression) : t("newFormula");

  // Auto-open on mount when freshly inserted via the toolbar.
  useEffect(() => {
    if (!shouldAutoOpen.current) return;
    const rafId = requestAnimationFrame(() => setOpen(true));
    return () => cancelAnimationFrame(rafId);
  }, []);

  const openPanel = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setOpen(true);
  }, []);

  // Close on Escape — delete node if it was never given an expression
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
        if (node.attrs.expression === "") deleteNode();
      }
    };
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [open, node.attrs.expression, deleteNode]);

  const handleConfirm = (newExpr: string) => {
    updateAttributes({ expression: newExpr });
    setOpen(false);
  };

  const handleCancel = () => {
    setOpen(false);
    if (node.attrs.expression === "") deleteNode();
  };

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
            <Badge
              variant="formula"
              className="inline-flex flex-nowrap items-center gap-1 px-1.5 py-0 border-dashed cursor-pointer hover:bg-amber-500/20 mr-0.5 transition-all duration-150 active:scale-95"
              // Use onMouseDown instead of onClick — ProseMirror's drag-handle
              // intercepts mousedown on atom nodes before React's onClick fires.
              onMouseDown={openPanel}
              role="button"
              tabIndex={0}
              onKeyDown={(e: React.KeyboardEvent) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  openPanel(e as unknown as React.MouseEvent);
                }
              }}
            >
              <SquareFunction className="w-2.5 h-2.5 flex-shrink-0" />
              {/* Raw <span>: colored Badge inside contentEditable; <Text as="span">
                  would reset the inherited pill color and text-[11px] is sub-xs
                  grid geometry. Kept raw for correctness. */}
              {/* eslint-disable-next-line react/forbid-elements -- span inside a colored Badge in TipTap contentEditable; Text as="span" would reset the inherited pill color and text-[11px] is sub-xs grid geometry */}
              <span className="font-mono text-[11px] leading-none">{preview}</span>
            </Badge>
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

      {open &&
        createPortal(
          <Flex
            align="center"
            justify="center"
            className="fixed inset-0 z-[999] p-4"
            onMouseDown={(e) => e.stopPropagation()}
          >
            {/* Backdrop — intentionally has no click handler to prevent accidental close */}
            <Box className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

            {/* Modal panel */}
            <Box className="relative rounded-lg border border-border bg-popover shadow-2xl max-h-[90vh] overflow-y-auto w-full max-w-[min(660px,90vw)]">
              <Suspense fallback={<Skeleton className="h-64 w-full" />}>
                <FormulaEditorPanel
                  mode="edit"
                  initialExpr={expression}
                  onConfirm={handleConfirm}
                  onCancel={handleCancel}
                />
              </Suspense>
            </Box>
          </Flex>,
          document.body,
        )}
    </NodeViewWrapper>
  );
}
