import { PageEditorShell } from "@/components/page-editor-shell";
import { useRouter } from "@/hooks/use-router";

interface EditPageClientProps {
  pageId: string;
}

export function EditPageClient({ pageId }: EditPageClientProps) {
  const router = useRouter();
  const back = () => router.push("/pages");
  return <PageEditorShell pageId={pageId} onClose={back} onSave={back} />;
}
