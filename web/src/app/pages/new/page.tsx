"use client";

import { useSearchParams } from "next/navigation";
import { PageBuilder } from "@/components/page-builder";
import { PageLayout } from "@/components/page-layout";
import { useViewTransition } from "@/hooks/use-view-transition";
import type { DeviceType } from "@/lib/api";

export default function NewPage() {
  const { push } = useViewTransition();
  const searchParams = useSearchParams();
  const deviceType = (searchParams.get("device") as DeviceType) || "flagship";

  const handleClose = () => {
    push("/pages", { transitionType: "slide-down" });
  };

  const handleSave = () => {
    push("/pages", { transitionType: "slide-down" });
  };

  return (
    <PageLayout outerClassName="flex flex-col" className="flex-1 flex flex-col min-h-0">
      <PageBuilder
        deviceType={deviceType}
        onClose={handleClose}
        onSave={handleSave}
      />
    </PageLayout>
  );
}

