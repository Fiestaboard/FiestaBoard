import { Box, Code, Heading, PageHeader, PageSection, Text } from "@fiestaboard/ui";
import { Activity } from "lucide-react";

import { FlatPage } from "@/components/section-shell";
import { useTranslations } from "@/i18n/translations";

export default function DebugMonitorPage() {
  const t = useTranslations("monitor");
  return (
    // `title` and `icon` used to be passed to PageLayout, which has neither
    // prop — they were silently dropped and this route rendered no <h1> at
    // all. PageHeader is the component that owns the page title everywhere
    // else in the app.
    <FlatPage>
      <PageHeader icon={Activity} title={t("title")} description={t("monitoringRemovedTitle")} />
      <PageSection>
        <Box className="py-8 text-center">
          <Activity className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <Heading level={2} size="lg" className="mb-2">
            {t("monitoringRemovedTitle")}
          </Heading>
          <Text tone="muted" className="max-w-lg mx-auto">
            {t("monitoringRemovedDescription")} <Code>docker logs fiestaboard</Code>
          </Text>
        </Box>
      </PageSection>
    </FlatPage>
  );
}
