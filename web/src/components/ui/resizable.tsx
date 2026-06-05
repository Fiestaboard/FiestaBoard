"use client";

import { GripVertical } from "lucide-react";
import * as ResizablePrimitive from "react-resizable-panels";

import { cn } from "@/lib/utils";

const ResizablePanelGroup = ({ className, ...props }: React.ComponentProps<typeof ResizablePrimitive.PanelGroup>) => (
  <ResizablePrimitive.PanelGroup
    className={cn("flex h-full w-full data-[panel-group-direction=vertical]:flex-col", className)}
    {...props}
  />
);

const ResizablePanel = ResizablePrimitive.Panel;

const ResizableHandle = ({
  withHandle,
  className,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.PanelResizeHandle> & {
  withHandle?: boolean;
}) => (
  // The handle is intentionally a 0-width "spacer" that delegates its
  // visual to the adjacent panel's own border (e.g. the AI chat
  // Card's left edge). The `after:` element creates a generous
  // invisible hit area so the user can grab the seam without seeing
  // a separate divider line. Hovering brightens both the hit area
  // and the small grip thumb so the user gets clear affordance.
  <ResizablePrimitive.PanelResizeHandle
    className={cn(
      "group/resize relative flex w-0 items-center justify-center transition-colors",
      "after:absolute after:inset-y-0 after:left-1/2 after:w-2 after:-translate-x-1/2",
      "after:transition-colors hover:after:bg-brand-emphasis/30",
      "data-[resize-handle-state=drag]:after:bg-brand-emphasis/60",
      "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
      "data-[panel-group-direction=vertical]:h-0 data-[panel-group-direction=vertical]:w-full",
      "data-[panel-group-direction=vertical]:after:left-0 data-[panel-group-direction=vertical]:after:h-2",
      "data-[panel-group-direction=vertical]:after:w-full data-[panel-group-direction=vertical]:after:-translate-y-1/2",
      "data-[panel-group-direction=vertical]:after:translate-x-0",
      className,
    )}
    {...props}
  >
    {withHandle && (
      <div className="pointer-events-none z-10 flex h-7 w-1 items-center justify-center rounded-full bg-muted-foreground/40 opacity-0 transition-opacity group-hover/resize:opacity-100 group-data-[resize-handle-state=drag]/resize:opacity-100">
        <GripVertical className="h-3 w-3 text-muted-foreground opacity-0" />
      </div>
    )}
  </ResizablePrimitive.PanelResizeHandle>
);

export { ResizableHandle, ResizablePanel, ResizablePanelGroup };
