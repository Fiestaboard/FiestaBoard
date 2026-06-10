import { PageEditorShell } from "@/components/page-editor-shell";
import { useSearchParams } from "@/hooks/use-router";
import { useViewTransition } from "@/hooks/use-view-transition";
import type { DeviceType } from "@/lib/api";

export default function NewPage() {
  const { push } = useViewTransition();
  const searchParams = useSearchParams();
  const deviceType = (searchParams.get("device") as DeviceType) || "flagship";
  const skipDraft = searchParams.get("fresh") === "1";

  const back = () => push("/pages", { transitionType: "slide-down" });

  return <PageEditorShell deviceType={deviceType} skipDraft={skipDraft} onClose={back} onSave={back} />;
}
