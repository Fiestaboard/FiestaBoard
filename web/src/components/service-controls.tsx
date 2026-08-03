"use client";

import { Badge, Card, CardContent, CardHeader, CardTitle, Flex, Skeleton, Text } from "@fiestaboard/ui";

import { useStatus } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";

export function ServiceControls() {
  const t = useTranslations("serviceControls");
  const tc = useTranslations("common");
  const { data: status, isLoading } = useStatus();

  const isRunning = status?.running ?? false;

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="px-4 sm:px-6">
          <CardTitle className="text-base sm:text-lg">{t("title")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 px-4 sm:px-6">
          <Skeleton className="h-5 w-full max-w-[200px]" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="px-4 sm:px-6">
        <Flex align="center" justify="between">
          <CardTitle className="text-base sm:text-lg">{t("title")}</CardTitle>
          <Badge
            variant={isRunning ? "default" : "secondary"}
            className={`text-xs ${isRunning ? "bg-brand/15 text-brand border-brand/25 hover:bg-brand/20" : ""}`}
          >
            {isRunning ? tc("running") : tc("stopped")}
          </Badge>
        </Flex>
      </CardHeader>
      <CardContent className="space-y-4 px-4 sm:px-6">
        <Text tone="muted" size="xs">
          {t("contentAutoSent")}
        </Text>
      </CardContent>
    </Card>
  );
}
