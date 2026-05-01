"use client";

import { Activity } from "lucide-react";
import { useTranslations } from "next-intl";
import { PageLayout } from "@/components/page-layout";
import { Card, CardContent } from "@/components/ui/card";

export default function DebugMonitorPage() {
  const t = useTranslations("monitor");
  return (
    <PageLayout title={t("title")} icon={Activity}>
        <Card>
          <CardContent className="py-12 text-center">
            <Activity className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h2 className="text-lg font-semibold mb-2">{t("monitoringRemovedTitle")}</h2>
            <p className="text-sm text-muted-foreground max-w-lg mx-auto">
              {t("monitoringRemovedDescription")}{" "}
              <code className="px-1.5 py-0.5 rounded bg-muted font-mono text-xs">docker logs fiestaboard</code>
            </p>
          </CardContent>
        </Card>
    </PageLayout>
  );
}
