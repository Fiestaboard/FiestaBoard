"use client";

import {
  Badge,
  Box,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Flex,
  Skeleton,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { Cpu, ExternalLink, Info, Package } from "lucide-react";

import { useStatus } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
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
          <Flex align="center" justify="between" gap="4">
            <dt className="text-muted-foreground">{t("status")}</dt>
            <dd>
              {isLoadingStatus ? (
                <Skeleton className="h-5 w-16" />
              ) : (
                <Flex align="center" gap="2">
                  <Text
                    as="span"
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
                </Flex>
              )}
            </dd>
          </Flex>

          <Flex align="center" justify="between" gap="4">
            <dt className="text-muted-foreground">{t("version")}</dt>
            <dd>
              {isLoadingVersion ? (
                <Skeleton className="h-5 w-16" />
              ) : versionData ? (
                <Flex align="center" gap="2">
                  <Package className="h-3.5 w-3.5 text-muted-foreground" />
                  <Text as="span" className="font-mono tabular-nums">
                    v{versionData.package_version}
                  </Text>
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
                </Flex>
              ) : (
                <Text as="span" tone="muted">
                  —
                </Text>
              )}
            </dd>
          </Flex>

          {versionData?.build_version && (
            <Flex align="center" justify="between" gap="4">
              <dt className="text-muted-foreground">{t("buildVersion")}</dt>
              <dd className="font-mono text-xs text-muted-foreground tabular-nums">{versionData.build_version}</dd>
            </Flex>
          )}

          {versionData?.hardware_model && (
            <Flex align="center" justify="between" gap="4">
              <dt className="text-muted-foreground">{t("hardware")}</dt>
              <dd className="flex items-center gap-2">
                <Cpu className="h-3.5 w-3.5 text-muted-foreground" />
                <Text as="span" size="xs">
                  {versionData.hardware_model}
                </Text>
              </dd>
            </Flex>
          )}

          <Box className="pt-2 border-t">
            <TextLink
              href="https://fiestaboard.app/docs/intro"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-primary no-underline hover:underline"
            >
              {t("viewDocs")}
              <ExternalLink className="h-3.5 w-3.5" />
            </TextLink>
          </Box>
        </dl>
      </CardContent>
    </Card>
  );
}
