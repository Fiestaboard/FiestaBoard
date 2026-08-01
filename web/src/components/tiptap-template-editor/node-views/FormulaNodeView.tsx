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

import { Badge, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@fiestaboard/ui";
import { NodeViewWrapper } from "@tiptap/react";
import { SquareFunction } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useTranslations } from "@/i18n/translations";

import { FormulaEditorPanel } from "../components/FormulaEditorPanel";

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
              <span className="font-mono text-[11px] leading-none">{preview}</span>
            </Badge>
          </TooltipTrigger>
          <TooltipContent>
            <p className="font-mono text-xs">{"{{= " + expression + " }}"}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("clickToEditFormula")}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {open &&
        createPortal(
          <div
            className="fixed inset-0 z-[999] flex items-center justify-center p-4"
            onMouseDown={(e) => e.stopPropagation()}
          >
            {/* Backdrop — intentionally has no click handler to prevent accidental close */}
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

            {/* Modal panel */}
            <div className="relative rounded-lg border border-border bg-popover shadow-2xl max-h-[90vh] overflow-y-auto w-full max-w-[min(660px,90vw)]">
              <FormulaEditorPanel
                mode="edit"
                initialExpr={expression}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
              />
            </div>
          </div>,
          document.body,
        )}
    </NodeViewWrapper>
  );
}
