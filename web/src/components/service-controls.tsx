"use client";

import { useTranslations } from "@/i18n/translations";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useStatus } from "@/hooks/use-board";

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
        <div className="flex items-center justify-between">
          <CardTitle className="text-base sm:text-lg">{t("title")}</CardTitle>
          <Badge
            variant={isRunning ? "default" : "secondary"}
            className={`text-xs ${isRunning ? "bg-brand/15 text-brand border-brand/25 hover:bg-brand/20" : ""}`}
          >
            {isRunning ? tc("running") : tc("stopped")}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 px-4 sm:px-6">
        <p className="text-[10px] text-muted-foreground">{t("contentAutoSent")}</p>
      </CardContent>
    </Card>
  );
}
