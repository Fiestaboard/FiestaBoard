"use client";

import { useRouter } from "next/navigation";
import { PageBuilder } from "@/components/page-builder";
import { PageLayout } from "@/components/page-layout";

interface EditPageClientProps {
  pageId: string;
}

export function EditPageClient({ pageId }: EditPageClientProps) {
  const router = useRouter();

  const handleClose = () => {
    router.push("/pages");
  };

  const handleSave = () => {
    router.push("/pages");
  };

  return (
    <PageLayout>
      <PageBuilder
        pageId={pageId}
        onClose={handleClose}
        onSave={handleSave}
      />
    </PageLayout>
  );
}

