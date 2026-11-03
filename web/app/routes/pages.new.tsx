import { PageEditorShell } from "@/components/page-editor-shell";
import { useSearchParams } from "@/hooks/use-router";
import { useViewTransition } from "@/hooks/use-view-transition";
import type { DeviceType } from "@/lib/api";

export default function NewPage() {
  const { push } = useViewTransition();
  const searchParams = useSearchParams();
  // An explicit display from the Pages filter wins over the sidebar selection.
  const deviceType = (searchParams.get("device") as DeviceType | null) || undefined;
  const targetBoardId = searchParams.get("board") || undefined;
  const skipDraft = searchParams.get("fresh") === "1";

  const back = () => push("/pages");

  return (
    <PageEditorShell
      pageKind={searchParams.get("kind") === "flexible" ? "flexible" : undefined}
      deviceType={deviceType}
      targetBoardId={targetBoardId}
      skipDraft={skipDraft}
      onClose={back}
      onSave={back}
    />
  );
}
