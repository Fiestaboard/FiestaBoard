"use client";

import { useSearchParams } from "next/navigation";
import { PageBuilder } from "@/components/page-builder";
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
    <div className="min-h-screen bg-background flex flex-col overflow-x-hidden">
      <div 
        className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 flex-1 flex flex-col min-h-0 max-w-full"
      >
        <PageBuilder
          deviceType={deviceType}
          onClose={handleClose}
          onSave={handleSave}
        />
      </div>
    </div>
  );
}

