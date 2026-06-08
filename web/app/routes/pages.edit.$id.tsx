import { useParams } from "@/hooks/use-router";

import { EditPageClient } from "@/components/pages/edit-page-client";

export default function EditPage() {
  const { id } = useParams<{ id: string }>();
  return <EditPageClient pageId={id ?? ""} />;
}
