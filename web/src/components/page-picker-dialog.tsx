"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Check } from "lucide-react";

interface Page {
  id: string;
  name: string;
  type?: string;
}

interface PagePickerDialogProps {
  pages: Page[];
  selectedPageId: string | null;
  onSelect: (pageId: string | null) => void;
  allowNone?: boolean;
}

/**
 * Simple page picker for selecting (not editing) pages.
 * Used for default page selection in schedule settings.
 */
export function PagePickerDialog({
  pages,
  selectedPageId,
  onSelect,
  allowNone = false,
}: PagePickerDialogProps) {
  return (
    <div className="space-y-2">
      {allowNone && (
        <button
          onClick={() => onSelect(null)}
          className={`w-full flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors ${
            selectedPageId === null ? "border-primary bg-muted/50" : ""
          }`}
        >
          <span className="text-sm font-medium">None (no default)</span>
          {selectedPageId === null && (
            <Check className="h-4 w-4 text-primary" />
          )}
        </button>
      )}
      
      {pages.map((page) => (
        <button
          key={page.id}
          onClick={() => onSelect(page.id)}
          className={`w-full flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors ${
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
            <Check className="h-4 w-4 text-primary" />
          )}
        </button>
      ))}
    </div>
  );
}
