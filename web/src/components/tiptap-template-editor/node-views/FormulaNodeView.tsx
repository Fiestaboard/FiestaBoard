/**
 * FormulaNodeView — React NodeView for Formula nodes.
 *
 * Renders as an amber badge pill showing Σ + truncated expression preview.
 * Clicking opens a floating FormulaEditorPanel anchored to the pill via a
 * portal into document.body (so it escapes the ProseMirror container).
 *
 * The panel does NOT close on outside click — only on Esc / Done / Cancel.
 */
"use client";

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { NodeViewWrapper } from '@tiptap/react';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Sigma } from 'lucide-react';
import { FormulaEditorPanel } from '../components/FormulaEditorPanel';
import { useTranslations } from 'next-intl';

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
  const [panelStyle, setPanelStyle] = useState<React.CSSProperties>({});
  const pillRef = useRef<HTMLSpanElement>(null);
  // Capture autoOpen at mount time so the effect doesn't depend on the prop
  // (calling updateAttributes would trigger a ProseMirror transaction that can
  // remount this component, cancelling the RAF before it fires).
  const shouldAutoOpen = useRef(autoOpen);

  const preview =
    expression.length > 0
      ? expression.length > 20 ? expression.slice(0, 20) + '\u2026' : expression
      : t("newFormula");

  /** Apply position from an already-retrieved DOMRect. */
  const applyPanelStyleFromRect = useCallback((rect: DOMRect) => {
    const PANEL_WIDTH = 392;
    let left = rect.left;
    let top = rect.bottom + 6;
    if (left + PANEL_WIDTH > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - PANEL_WIDTH - 8);
    }
    const PANEL_APPROX_HEIGHT = 480;
    if (top + PANEL_APPROX_HEIGHT > window.innerHeight - 8) {
      top = Math.max(8, rect.top - PANEL_APPROX_HEIGHT - 6);
    }
    setPanelStyle({ position: 'fixed', top, left, zIndex: 1000 });
  }, []);

  /** Compute and apply position from the pill's current DOMRect.
   *  Returns true if the rect was available and valid. */
  const computePanelStyle = useCallback((): boolean => {
    const rect = pillRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return false;
    applyPanelStyleFromRect(rect);
    return true;
  }, [applyPanelStyleFromRect]);

  // Auto-open on mount when freshly inserted (autoOpen attr).
  // We do NOT call updateAttributes here — that fires a ProseMirror transaction
  // which can remount this component and cancel the pending RAF.
  // Instead we use a ref captured at mount time and retry frames until the pill
  // has a valid DOMRect (width > 0), guarding against the "sometimes" timing race.
  useEffect(() => {
    if (!shouldAutoOpen.current) return;
    let rafId: number;
    let attempts = 0;
    const MAX_ATTEMPTS = 12; // ~200ms at 60fps

    const tryOpen = () => {
      attempts++;
      if (computePanelStyle()) {
        setOpen(true);
      } else if (attempts < MAX_ATTEMPTS) {
        rafId = requestAnimationFrame(tryOpen);
      }
      // If we exhaust retries, the insert silently no-ops rather than showing a broken panel.
    };

    rafId = requestAnimationFrame(tryOpen);
    return () => cancelAnimationFrame(rafId);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openPanel = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Re-compute position every time in case the editor scrolled
    computePanelStyle();
    setOpen(true);
  }, [computePanelStyle]);

  // Close on Escape — delete node if it was never given an expression
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        setOpen(false);
        if (node.attrs.expression === '') deleteNode();
      }
    };
    document.addEventListener('keydown', handleKeyDown, true);
    return () => document.removeEventListener('keydown', handleKeyDown, true);
  }, [open, node.attrs.expression, deleteNode]);

  const handleConfirm = (newExpr: string) => {
    updateAttributes({ expression: newExpr });
    setOpen(false);
  };

  const handleCancel = () => {
    setOpen(false);
    // If the user never set an expression, remove the placeholder node
    if (node.attrs.expression === '') deleteNode();
  };

  return (
    <NodeViewWrapper
      as="span"
      data-drag-handle
      style={{
        display: 'inline-flex',
        verticalAlign: 'baseline',
        whiteSpace: 'nowrap',
      }}
    >
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            {/* @ts-expect-error — Badge ref forwarding with span ref */}
            <Badge
              ref={pillRef}
              variant="formula"
              className="inline-flex flex-nowrap items-center gap-1 px-1.5 py-0 border-dashed cursor-pointer hover:bg-amber-500/20 mr-0.5 transition-all duration-150 active:scale-95"
              // Use onMouseDown instead of onClick — ProseMirror's drag-handle
              // intercepts mousedown on atom nodes before React's onClick fires.
              // preventDefault stops PM from handling the event.
              onMouseDown={openPanel}
              role="button"
              tabIndex={0}
              onKeyDown={(e: React.KeyboardEvent) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  openPanel(e as unknown as React.MouseEvent);
                }
              }}
            >
              <Sigma className="w-2.5 h-2.5 flex-shrink-0" />
              <span className="font-mono text-[11px] leading-none">{preview}</span>
            </Badge>
          </TooltipTrigger>
          <TooltipContent>
            <p className="font-mono text-xs">{'{{= ' + expression + ' }}'}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("clickToEditFormula")}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      {open &&
        createPortal(
          <div
            style={panelStyle}
            className="rounded-lg border border-border bg-popover shadow-xl"
            // Prevent clicks inside the panel from propagating to the editor
            onMouseDown={(e) => e.stopPropagation()}
          >
            <FormulaEditorPanel
              mode="edit"
              initialExpr={expression}
              onConfirm={handleConfirm}
              onCancel={handleCancel}
            />
          </div>,
          document.body
        )}
    </NodeViewWrapper>
  );
}
