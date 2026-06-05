import { EditPageClient } from "./edit-page-client";

// Required for static export with dynamic routes
// Generate a placeholder page for static export - actual routing is handled client-side
export async function generateStaticParams() {
  return [{ id: "_placeholder" }];
}

export default async function EditPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = await params;
  return <EditPageClient pageId={resolvedParams.id} />;
}
