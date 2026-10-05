import { PageEditorShell } from "@/components/page-editor-shell";
import { useSearchParams } from "@/hooks/use-router";
import { useViewTransition } from "@/hooks/use-view-transition";
import type { DeviceType } from "@/lib/api";

export default function NewPage() {
  const { push } = useViewTransition();
  const searchParams = useSearchParams();
  // No `?device=`: the editor targets the display selected in the sidebar.
  const deviceType = (searchParams.get("device") as DeviceType | null) || undefined;
  const skipDraft = searchParams.get("fresh") === "1";

  const back = () => push("/pages", { transitionType: "slide-down" });

  return <PageEditorShell deviceType={deviceType} skipDraft={skipDraft} onClose={back} onSave={back} />;
}
