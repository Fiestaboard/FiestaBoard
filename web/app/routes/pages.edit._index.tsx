import { Text } from "@fiestaboard/ui";
import { useEffect } from "react";

import { PageEditorShell } from "@/components/page-editor-shell";
import { useSearchParams } from "@/hooks/use-router";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";

export default function EditPage() {
  const tCommon = useTranslations("common");
  const { push } = useViewTransition();

  // Search-only navigation keeps this route mounted. Follow the router's
  // committed ID, after the editor's unsaved-changes guard allows navigation.
  const pageId = useSearchParams().get("id");

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

  // A different document gets fresh form state, even if its fetch fails.
  return <PageEditorShell key={pageId} pageId={pageId} onClose={handleClose} onSave={handleSave} />;
}
