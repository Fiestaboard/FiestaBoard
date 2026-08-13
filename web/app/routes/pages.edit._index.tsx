import { PageLayout, Text } from "@fiestaboard/ui";
import { useEffect, useState } from "react";

import { PageBuilder } from "@/components/page-builder";
import { useViewTransition } from "@/hooks/use-view-transition";

/** Read the `?id` query parameter (works with the static SPA build). */
function readPageIdFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("id");
}

export default function EditPage() {
  const { push } = useViewTransition();

  // Read the id in the state initializer, not a mount effect: the effect
  // version always rendered "Loading…" once even when the id was right there
  // in the URL (react-hooks/set-state-in-effect, issue #1568). The redirect
  // stays in an effect — navigating during render is not allowed.
  const [pageId] = useState(readPageIdFromUrl);

  useEffect(() => {
    if (!pageId) {
      push("/pages", { transitionType: "slide-down" });
    }
  }, [pageId, push]);

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
