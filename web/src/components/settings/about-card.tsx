"use client";

import { useQuery } from "@tanstack/react-query";
import { Cpu, ExternalLink, Info, Package } from "lucide-react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useStatus } from "@/hooks/use-board";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export function AboutCard() {
  const t = useTranslations("profile");

  const { data: versionData, isLoading: isLoadingVersion } = useQuery({
    queryKey: ["version"],
    queryFn: () => api.getVersion(),
    staleTime: Infinity,
    retry: false,
  });

  const { data: updateCheck } = useQuery({
    queryKey: ["update-check"],
    queryFn: () => api.checkForUpdate(),
    staleTime: 1000 * 60 * 60,
    retry: false,
  });

  const { data: statusData, isLoading: isLoadingStatus } = useStatus();
  const isRunning = statusData?.running ?? false;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Info className="h-4 w-4" />
          {t("aboutTitle")}
        </CardTitle>
        <CardDescription>{t("aboutDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="space-y-3 text-sm">
          <div className="flex items-center justify-between gap-4">
            <dt className="text-muted-foreground">{t("status")}</dt>
            <dd>
              {isLoadingStatus ? (
                <Skeleton className="h-5 w-16" />
              ) : (
                <div className="flex items-center gap-2">
                  <span
                    className={cn("h-2 w-2 rounded-full", isRunning ? "bg-board-green" : "bg-muted-foreground")}
                    style={
                      isRunning
                        ? {
                            boxShadow: "0 0 6px color-mix(in oklch, var(--color-board-green) 50%, transparent)",
                          }
                        : undefined
                    }
                  />
                  <Badge
                    variant={isRunning ? "default" : "secondary"}
                    className={cn("text-xs", isRunning && "bg-brand/15 text-brand border-brand/25 hover:bg-brand/20")}
                  >
                    {isRunning ? t("statusRunning") : t("statusStopped")}
                  </Badge>
                </div>
              )}
            </dd>
          </div>

          <div className="flex items-center justify-between gap-4">
            <dt className="text-muted-foreground">{t("version")}</dt>
            <dd>
              {isLoadingVersion ? (
                <Skeleton className="h-5 w-16" />
              ) : versionData ? (
                <div className="flex items-center gap-2">
                  <Package className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="font-mono tabular-nums">v{versionData.package_version}</span>
                  {versionData.is_dev && (
                    <Badge variant="secondary" className="text-xs">
                      {t("devBuild")}
                    </Badge>
                  )}
                  {updateCheck?.update_available && (
                    <Badge variant="outline" className="text-xs text-warning border-warning/50">
                      v{updateCheck.latest_version} available
                    </Badge>
                  )}
                </div>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </dd>
          </div>

          {versionData?.build_version && (
            <div className="flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">{t("buildVersion")}</dt>
              <dd className="font-mono text-xs text-muted-foreground tabular-nums">{versionData.build_version}</dd>
            </div>
          )}

          {versionData?.hardware_model && (
            <div className="flex items-center justify-between gap-4">
              <dt className="text-muted-foreground">{t("hardware")}</dt>
              <dd className="flex items-center gap-2">
                <Cpu className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs">{versionData.hardware_model}</span>
              </dd>
            </div>
          )}

          <div className="pt-2 border-t">
            <a
              href="https://fiestaboard.app/docs/intro"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
            >
              {t("viewDocs")}
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
