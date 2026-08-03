"use client";

import { Flex, Text, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpCircle, Package } from "lucide-react";

import { useTranslations } from "@/i18n/translations";
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
    <Flex align="center" gap="2" className="text-xs text-muted-foreground">
      <Package className="h-3 w-3" />
      <Text as="span" size="xs" tone="muted" suppressHydrationWarning>
        v{version.package_version}
        {version.is_dev && ` ${t("devSuffix")}`}
      </Text>
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
              <Text>{t("updateAvailableTooltip", { version: updateCheck.latest_version ?? "" })}</Text>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </Flex>
  );
}
