"use client";

import { Text } from "@fiestaboard/ui";
import { Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

/** FiestaBot's decorative mark. Only live work animates; CSS honors reduced motion. */
export function AiBotMark({ active = false, className }: { active?: boolean; className?: string }) {
  return (
    <Text
      as="span"
      aria-hidden="true"
      data-active={active || undefined}
      className={cn(
        "fiestabot-mark relative inline-flex size-9 shrink-0 items-center justify-center rounded-xl",
        className,
      )}
    >
      <Sparkles className="relative size-[55%]" />
    </Text>
  );
}
