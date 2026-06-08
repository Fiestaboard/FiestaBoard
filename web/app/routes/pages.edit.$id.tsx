/**
 * Route module for `/pages/edit/:id`. In Next.js App Router, the
 * canonical `page.tsx` is a server-async wrapper that awaits `params`
 * before passing `pageId` to the `EditPageClient`. RR7 client-only
 * routes get params synchronously via `useParams()`, so we render
 * the client component directly here.
 */
import { useParams } from "react-router";

import { EditPageClient } from "@/app/pages/edit/[id]/edit-page-client";

export default function EditPageRoute() {
  const params = useParams<{ id: string }>();
  return <EditPageClient pageId={params.id ?? ""} />;
}
