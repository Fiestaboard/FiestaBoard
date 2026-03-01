"use client";

import { Badge } from "@/components/ui/badge";
import { Check, GalleryHorizontalEnd, LayoutTemplate } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import type { Carousel } from "@/lib/api";
import { isCarouselId } from "@/lib/api";

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
  const hasCarousels = carousels.length > 0;
  const defaultTab = selectedPageId && isCarouselId(selectedPageId) ? "carousels" : "pages";

  const noneOption = allowNone && (
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
  );

  const pagesList = (
    <div className="space-y-2" role="listbox" aria-label="Pages">
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

  const carouselsList = (
    <div className="space-y-2" role="listbox" aria-label="Carousels">
      {carousels.map((carousel) => (
        <button
          key={carousel.id}
          role="option"
          aria-selected={selectedPageId === carousel.id}
          onClick={() => onSelect(carousel.id)}
          className={`w-full flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            selectedPageId === carousel.id ? "border-primary bg-muted/50" : ""
          }`}
        >
          <div className="flex items-center gap-2">
            <GalleryHorizontalEnd className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">{carousel.name}</span>
            <Badge variant="secondary" className="text-[10px]">
              {carousel.page_ids.length} {carousel.page_ids.length === 1 ? "page" : "pages"}
            </Badge>
          </div>
          {selectedPageId === carousel.id && (
            <Check className="h-4 w-4 text-primary" aria-hidden="true" />
          )}
        </button>
      ))}
    </div>
  );

  if (!hasCarousels) {
    return (
      <div className="space-y-2">
        {noneOption}
        {pagesList}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {noneOption}
      <Tabs defaultValue={defaultTab}>
        <TabsList className="w-full">
          <TabsTrigger value="pages" className="flex-1 gap-1.5">
            <LayoutTemplate className="h-4 w-4" />
            Pages ({pages.length})
          </TabsTrigger>
          <TabsTrigger value="carousels" className="flex-1 gap-1.5">
            <GalleryHorizontalEnd className="h-4 w-4" />
            Carousels ({carousels.length})
          </TabsTrigger>
        </TabsList>
        <TabsContent value="pages">
          {pagesList}
        </TabsContent>
        <TabsContent value="carousels">
          {carouselsList}
        </TabsContent>
      </Tabs>
    </div>
  );
}
