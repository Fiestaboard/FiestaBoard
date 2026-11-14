import { Alert, AlertDescription, AlertTitle, Box, Button, PageHeader, PageLayout, Stack } from "@fiestaboard/ui";
import { Home as HomeIcon, Info, PencilLine } from "lucide-react";
import { useEffect, useState } from "react";

import { ActivePageDisplay } from "@/components/active-page-display";
import { BoardInitErrorBanner } from "@/components/board-init-error-banner";
import { HomeCompose } from "@/components/home/home-compose";
import { SilenceImminentBanner } from "@/components/silence-imminent-banner";
import { useWizard } from "@/components/wizard-provider";
import { useTranslations } from "@/i18n/translations";
import { getSetupStatus } from "@/lib/setup-detection";

/**
 * Home (03 `33:10`, 07a §3). The PageHeader holds the ONE Compose entry
 * (CANON: Compose has exactly one entry point per platform); Change Page is
 * the Now showing card's in-content secondary action. Layout only: the shell
 * (nav, rail, bottom nav) is slice 2.1's.
 */
export default function Home() {
  const [boardNotConfigured, setBoardNotConfigured] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const { triggerWizard } = useWizard();
  const t = useTranslations("home");

  useEffect(() => {
    getSetupStatus()
      .then((status) => {
        if (status && !status.valid) {
          setBoardNotConfigured(true);
        }
      })
      .catch(() => {
        // Silently ignore - getSetupStatus already logs errors
      });
  }, []);

  return (
    <PageLayout outerClassName="relative" className="relative z-10">
      <PageHeader icon={HomeIcon} title={t("title")} description={t("description")} hue="orange">
        <Button variant="brand" onClick={() => setComposeOpen(true)} className="gap-2 max-sm:h-11">
          <PencilLine className="size-4" aria-hidden="true" />
          {t("compose")}
        </Button>
      </PageHeader>

      <Stack gap="4" className="mt-6">
        {boardNotConfigured && (
          <Alert className="border-info/50 bg-info/10 flex flex-col sm:flex-row sm:items-center sm:gap-4 [&>svg]:static [&>svg]:shrink-0 [&>svg+div]:translate-y-0 [&>svg~*]:pl-3">
            <Info className="h-4 w-4 text-info" />
            <Box className="flex-1 min-w-0">
              <AlertTitle>{t("noBoardConfigured")}</AlertTitle>
              <AlertDescription>{t("noBoardDescription")}</AlertDescription>
            </Box>
            <Button
              variant="brand"
              size="sm"
              onClick={triggerWizard}
              className="w-fit btn-lift shrink-0 self-center sm:self-center"
            >
              {t("runSetupWizard")}
            </Button>
          </Alert>
        )}

        <BoardInitErrorBanner />
        <SilenceImminentBanner />
        <ActivePageDisplay onCompose={() => setComposeOpen(true)} />
      </Stack>

      <HomeCompose open={composeOpen} onOpenChange={setComposeOpen} />
    </PageLayout>
  );
}
