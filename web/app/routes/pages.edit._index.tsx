import { PageLayout, Text } from "@fiestaboard/ui";
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
      <PageLayout>
        <Text tone="muted" className="text-center">
          Loading...
        </Text>
      </PageLayout>
    );
  }

  return (
    <PageLayout outerClassName="flex flex-col" className="flex-1 flex flex-col min-h-0">
      <PageBuilder pageId={pageId} onClose={handleClose} onSave={handleSave} />
    </PageLayout>
  );
}
