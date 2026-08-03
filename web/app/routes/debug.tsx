import { Card, CardContent, Code, Heading, PageLayout, Text } from "@fiestaboard/ui";
import { Activity } from "lucide-react";

import { useTranslations } from "@/i18n/translations";

export default function DebugMonitorPage() {
  const t = useTranslations("monitor");
  return (
    <PageLayout title={t("title")} icon={Activity}>
      <Card>
        <CardContent className="py-12 text-center">
          <Activity className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <Heading level={2} size="lg" className="mb-2">
            {t("monitoringRemovedTitle")}
          </Heading>
          <Text tone="muted" className="max-w-lg mx-auto">
            {t("monitoringRemovedDescription")} <Code>docker logs fiestaboard</Code>
          </Text>
        </CardContent>
      </Card>
    </PageLayout>
  );
}
