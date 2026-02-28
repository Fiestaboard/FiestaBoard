"use client";

import { Badge } from "@/components/ui/badge";
import { Check, GalleryHorizontalEnd } from "lucide-react";
import type { Carousel } from "@/lib/api";

interface Page {
  id: string;
  name: string;
  type?: string;
}

interface PagePickerDialogProps {
  pages: Page[];
  carousels?: Carousel[];
  selectedPageId: string | null;
  onSelect: (pageId: string | null) => void;
  allowNone?: boolean;
}

/**
 * Simple page/carousel picker for selecting (not editing) pages or carousels.
 * Used for default page selection in schedule settings and schedule entry form.
 */
export function PagePickerDialog({
  pages,
  carousels = [],
  selectedPageId,
  onSelect,
  allowNone = false,
}: PagePickerDialogProps) {
  return (
    <div className="space-y-2" role="listbox" aria-label="Page selection">
      {allowNone && (
        <button
          role="option"
          aria-selected={selectedPageId === null}
          onClick={() => onSelect(null)}
          className={`w-full flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            selectedPageId === null ? "border-primary bg-muted/50" : ""
          }`}
        >
          <span className="text-sm font-medium">None (no default)</span>
          {selectedPageId === null && (
            <Check className="h-4 w-4 text-primary" aria-hidden="true" />
          )}
        </button>
      )}

      {/* Carousels */}
      {carousels.length > 0 && (
        <>
          <div className="text-xs font-medium text-muted-foreground pt-2 pb-1">CAROUSELS</div>
          {carousels.map((carousel) => (
            <button
              key={carousel.id}
              onClick={() => onSelect(carousel.id)}
              className={`w-full flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors ${
                selectedPageId === carousel.id ? "border-primary bg-muted/50" : ""
              }`}
            >
              <div className="flex items-center gap-2">
                <GalleryHorizontalEnd className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">{carousel.name}</span>
                <Badge variant="secondary" className="text-[10px]">
                  {carousel.page_ids.length} pages
                </Badge>
              </div>
              {selectedPageId === carousel.id && (
                <Check className="h-4 w-4 text-primary" />
              )}
            </button>
          ))}
        </>
      )}

      {/* Pages */}
      {carousels.length > 0 && (
        <div className="text-xs font-medium text-muted-foreground pt-2 pb-1">PAGES</div>
      )}
      {pages.map((page) => (
        <button
          key={page.id}
          role="option"
          aria-selected={selectedPageId === page.id}
          onClick={() => onSelect(page.id)}
          className={`w-full flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            selectedPageId === page.id ? "border-primary bg-muted/50" : ""
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{page.name}</span>
            {page.type && (
              <Badge variant="secondary" className="text-[10px]">
                {page.type}
              </Badge>
            )}
          </div>
          {selectedPageId === page.id && (
            <Check className="h-4 w-4 text-primary" aria-hidden="true" />
          )}
        </button>
      ))}
    </div>
  );
}
