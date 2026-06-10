import { EditPageClient } from "@/components/pages/edit-page-client";
import { useParams } from "@/hooks/use-router";

export default function EditPage() {
  const { id } = useParams<{ id: string }>();
  return <EditPageClient pageId={id ?? ""} />;
}
