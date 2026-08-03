"use client";

import { Skeleton, Text, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@fiestaboard/ui";

import { useStatus } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";

export function ServiceStatus() {
  const { data, isLoading, isError } = useStatus();
  const t = useTranslations("serviceStatus");

  if (isLoading) {
    return <Skeleton className="h-3 w-3 rounded-full" />;
  }

  const statusText =
    isError || !data ? t("disconnectedTooltip") : data.running ? t("runningTooltip") : t("stoppedTooltip");

  const ariaLabel =
    isError || !data ? t("disconnectedAriaLabel") : data.running ? t("runningAriaLabel") : t("stoppedAriaLabel");

  const statusClass =
    isError || !data ? "bg-board-red animate-pulse" : data.running ? "bg-board-green" : "bg-muted-foreground";

  const glowStyle =
    isError || !data
      ? { boxShadow: "0 0 6px color-mix(in oklch, var(--color-board-red) 50%, transparent)" }
      : data.running
        ? { boxShadow: "0 0 6px color-mix(in oklch, var(--color-board-green) 50%, transparent)" }
        : undefined;

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            className="relative h-6 w-6 flex items-center justify-center cursor-default rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={ariaLabel}
          >
            <Text as="span" className={`h-3 w-3 rounded-full ${statusClass} transition-all`} style={glowStyle} />
          </button>
        </TooltipTrigger>
        <TooltipContent>
          <Text>{statusText}</Text>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
