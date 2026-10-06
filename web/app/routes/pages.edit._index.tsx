import { Text } from "@fiestaboard/ui";
import { useEffect, useState } from "react";

import { PageBuilder } from "@/components/page-builder";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";

/** Read the `?id` query parameter (works with the static SPA build). */
function readPageIdFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("id");
}

export default function EditPage() {
  const tCommon = useTranslations("common");
  const { push } = useViewTransition();

  // Read the id in the state initializer, not a mount effect: the effect
  // version always rendered "Loading…" once even when the id was right there
  // in the URL (react-hooks/set-state-in-effect, issue #1568). The redirect
  // stays in an effect — navigating during render is not allowed.
  const [pageId] = useState(readPageIdFromUrl);

  useEffect(() => {
    if (!pageId) {
      push("/pages");
    }
  }, [pageId, push]);

  const handleClose = () => {
    push("/pages");
  };

  const handleSave = () => {
    push("/pages");
  };

  if (!pageId) {
    return (
      <Text tone="muted" className="py-6 text-center">
        {tCommon("loading")}
      </Text>
    );
  }

  return <PageBuilder embedded pageId={pageId} onClose={handleClose} onSave={handleSave} />;
}
