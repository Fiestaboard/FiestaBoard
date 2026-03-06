"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  /** Optional illustration (e.g. SVG) shown instead of icon when provided */
  illustration?: React.ReactNode;
  className?: string;
}

/**
 * Consistent empty state for lists and grids (e.g. no pages, no carousels).
 * Use with an icon, title, optional description, optional CTA, and optional illustration.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  illustration,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center py-8 px-4",
        className
      )}
      role="status"
      aria-label={title}
    >
      {illustration ? (
        <div className="mb-3 flex items-center justify-center [&_svg]:max-w-[120px] [&_svg]:max-h-[80px] [&_svg]:text-muted-foreground" aria-hidden>
          {illustration}
        </div>
      ) : (
        <div className="rounded-full bg-brand/10 p-4 mb-3">
          <Icon className="h-8 w-8 text-brand" aria-hidden />
        </div>
      )}
      <h3 className="text-sm font-medium text-foreground">{title}</h3>
      {description && (
        <p className="text-sm text-muted-foreground mt-1 max-w-sm leading-relaxed">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
