"use client";

import { usePathname } from "next/navigation";
import FadeContent from "@/components/ui/react-bits/fade-content";

export function PageFadeWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <FadeContent key={pathname} duration={0.4} translateY={12}>
      {children}
    </FadeContent>
  );
}
