import { PageEditorShell } from "@/components/page-editor-shell";
import { useRouter, useSearchParams } from "@/hooks/use-router";
import { useViewTransition } from "@/hooks/use-view-transition";
import type { DeviceType } from "@/lib/api";

export default function NewPage() {
  const { push } = useViewTransition();
  const searchParams = useSearchParams();
  // An explicit display from the Pages filter wins over the sidebar selection.
  const deviceType = (searchParams.get("device") as DeviceType | null) || undefined;
  const targetBoardId = searchParams.get("board") || undefined;
  const skipDraft = searchParams.get("fresh") === "1";

  const { replace } = useRouter();
  const back = () => push("/pages");

  return (
    <PageEditorShell
      deviceType={deviceType}
      targetBoardId={targetBoardId}
      skipDraft={skipDraft}
      onClose={back}
      onSave={() => {}}
      // After the first save this is the page's editor, at its own URL:
      // reload, share and Back find it (BB-B-9).
      onCreated={(id) => replace(`/pages/edit/${encodeURIComponent(id)}`)}
    />
  );
}
