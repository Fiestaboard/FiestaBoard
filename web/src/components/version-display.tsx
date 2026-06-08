"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpCircle, Package } from "lucide-react";
import { useTranslations } from "@/i18n/translations";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";

export function VersionDisplay() {
  const t = useTranslations("versionDisplay");
  const { data: version } = useQuery({
    queryKey: ["version"],
    queryFn: () => api.getVersion(),
    staleTime: Infinity, // Version doesn't change often
    retry: false,
  });

  const { data: updateCheck } = useQuery({
    queryKey: ["update-check"],
    queryFn: () => api.checkForUpdate(),
    staleTime: 1000 * 60 * 60, // Check once per hour
    retry: false,
  });

  if (!version) return null;

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <Package className="h-3 w-3" />
      <span suppressHydrationWarning>
        v{version.package_version}
        {version.is_dev && ` ${t("devSuffix")}`}
      </span>
      {updateCheck?.update_available && (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={t("updateAvailableAriaLabel", { version: updateCheck.latest_version ?? "" })}
                className="inline-flex items-center rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <ArrowUpCircle className="h-3.5 w-3.5 text-warning" />
              </button>
            </TooltipTrigger>
            <TooltipContent>
              <p>{t("updateAvailableTooltip", { version: updateCheck.latest_version ?? "" })}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  );
}
