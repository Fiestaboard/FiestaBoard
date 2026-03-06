"use client";

import { useEffect, useState } from "react";
import { PageBuilder } from "@/components/page-builder";
import { useViewTransition } from "@/hooks/use-view-transition";

export default function EditPage() {
  const { push } = useViewTransition();
  const [pageId, setPageId] = useState<string | null>(null);

  useEffect(() => {
    // Read query parameter from URL (works with static export)
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const id = params.get("id");
      if (!id) {
        // Redirect to pages list if no ID provided
        push("/pages", { transitionType: "slide-down" });
      } else {
        setPageId(id);
      }
    }
  }, [push]);

  const handleClose = () => {
    push("/pages", { transitionType: "slide-down" });
  };

  const handleSave = () => {
    push("/pages", { transitionType: "slide-down" });
  };

  if (!pageId) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
          <div className="text-center text-muted-foreground">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col overflow-x-hidden">
      <div 
        className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 flex-1 flex flex-col min-h-0 max-w-full"
      >
        <PageBuilder
          pageId={pageId}
          onClose={handleClose}
          onSave={handleSave}
        />
      </div>
    </div>
  );
}

