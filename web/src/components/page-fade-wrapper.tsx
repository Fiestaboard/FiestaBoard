"use client";

import { usePathname } from "next/navigation";

import FadeContent from "@/components/ui/react-bits/fade-content";

export function PageFadeWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <FadeContent key={pathname} duration={0.4} translateY={12} className="flex-1 min-h-0 flex flex-col">
      {children}
    </FadeContent>
  );
}
