/**
 * Simple dropdown component for toolbar
 */
"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface ToolbarDropdownProps {
  label: string;
  icon?: React.ReactNode;
  children: React.ReactNode | ((close: () => void) => React.ReactNode);
  className?: string;
  onClose?: () => void;
  /** When false, clicking outside will NOT close the dropdown. Default: true */
  closeOnOutsideClick?: boolean;
}

export function ToolbarDropdown({
  label,
  icon,
  children,
  className,
  onClose,
  closeOnOutsideClick = true,
}: ToolbarDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [panelShift, setPanelShift] = useState(0);

  // The panel is plain `absolute top-full left-0` with no collision handling,
  // so a wide picker anchored to a right-side toolbar button runs off narrow
  // (mobile) viewports. Measure after open/content changes and shift it back
  // into view.
  useLayoutEffect(() => {
    if (!isOpen) {
      setPanelShift(0);
      return;
    }
    const clamp = () => {
      const panel = panelRef.current;
      if (!panel) return;
      // Measure the untransformed position so repeated clamps don't compound.
      const prevTransform = panel.style.transform;
      panel.style.transform = "none";
      const rect = panel.getBoundingClientRect();
      panel.style.transform = prevTransform;
      const viewportWidth = document.documentElement.clientWidth;
      const margin = 8;
      let shift = 0;
      if (rect.right > viewportWidth - margin) {
        shift = viewportWidth - margin - rect.right;
      }
      if (rect.left + shift < margin) {
        shift = margin - rect.left;
      }
      setPanelShift(shift);
    };
    clamp();
    // Pickers change width as the user switches tabs or filters, and rotation
    // changes the viewport — re-clamp on both.
    const observer = new ResizeObserver(clamp);
    if (panelRef.current) observer.observe(panelRef.current);
    window.addEventListener("resize", clamp);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", clamp);
    };
  }, [isOpen]);

  const handleClose = () => {
    setIsOpen(false);
    onClose?.();
  };

  // Close dropdown when clicking outside (only if closeOnOutsideClick is true)
  useEffect(() => {
    if (!isOpen || !closeOnOutsideClick) return;
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        onClose?.();
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen, closeOnOutsideClick, onClose]);

  // Always close on Escape
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        setIsOpen(false);
        onClose?.();
      }
    }
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [isOpen, onClose]);

  return (
    <TooltipProvider>
      <div ref={dropdownRef} className="relative">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => setIsOpen(!isOpen)}
              className={cn(
                "flex items-center justify-center p-1.5 rounded-md",
                "hover:bg-muted/50 transition-colors",
                "border border-transparent",
                isOpen && "bg-muted/70 border-border",
                className,
              )}
              aria-expanded={isOpen}
              aria-haspopup="true"
              aria-label={label || "Menu"}
            >
              {icon && <span className="w-4 h-4">{icon}</span>}
              {label && <span className="sr-only">{label}</span>}
            </button>
          </TooltipTrigger>
          {label && (
            <TooltipContent>
              <p>{label}</p>
            </TooltipContent>
          )}
        </Tooltip>

        {isOpen && (
          <div
            ref={panelRef}
            data-testid="toolbar-dropdown-panel"
            className="absolute top-full left-0 mt-1 z-50 bg-popover border border-border rounded-md shadow-lg max-w-[calc(100vw-16px)] overflow-x-auto"
            style={{ transform: panelShift ? `translateX(${panelShift}px)` : undefined }}
          >
            {typeof children === "function" ? children(handleClose) : children}
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
