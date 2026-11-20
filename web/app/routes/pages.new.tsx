import { PageEditorShell } from "@/components/page-editor-shell";
import { useReportCreatedPage } from "@/components/pages/created-page-context";
import { useSearchParams } from "@/hooks/use-router";
import { useViewTransition } from "@/hooks/use-view-transition";
import type { DeviceType } from "@/lib/api";
import { appUrl } from "@/lib/base-path";

export default function NewPage() {
  const { push } = useViewTransition();
  const searchParams = useSearchParams();
  // An explicit display from the Pages filter wins over the sidebar selection.
  const deviceType = (searchParams.get("device") as DeviceType | null) || undefined;
  const targetBoardId = searchParams.get("board") || undefined;
  const skipDraft = searchParams.get("fresh") === "1";

  const back = () => push("/pages");
  const reportCreated = useReportCreatedPage();

  return (
    <PageEditorShell
      deviceType={deviceType}
      targetBoardId={targetBoardId}
      skipDraft={skipDraft}
      onClose={back}
      onSave={() => {}}
      // After the first save this is the page's editor, at its own URL:
      // reload, share and Back find it (BB-B-9). Only the address changes:
      // a route change would remount the editor mid-flow (text typed during
      // the save, the Saved toast's Show now), so the router is not asked.
      onCreated={(id) => {
        window.history.replaceState(window.history.state, "", appUrl(`/pages/edit/${encodeURIComponent(id)}`));
        reportCreated?.(id);
      }}
    />
  );
}
