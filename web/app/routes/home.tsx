import { Alert, AlertDescription, AlertTitle, Button, PageHeader, PageLayout } from "@fiestaboard/ui";
import { Home as HomeIcon, Info } from "lucide-react";
import { useEffect, useState } from "react";

import { ActivePageDisplay } from "@/components/active-page-display";
import { SilenceImminentBanner } from "@/components/silence-imminent-banner";
import { useWizard } from "@/components/wizard-provider";
import { useTranslations } from "@/i18n/translations";
import { getSetupStatus } from "@/lib/setup-detection";

export default function Home() {
  const [boardNotConfigured, setBoardNotConfigured] = useState(false);
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
      <PageHeader icon={HomeIcon} title={t("title")} description={t("description")} />

      {boardNotConfigured && (
        <div className="mb-6">
          <Alert className="border-info/50 bg-info/10 flex flex-col sm:flex-row sm:items-center sm:gap-4 [&>svg]:static [&>svg]:shrink-0 [&>svg+div]:translate-y-0 [&>svg~*]:pl-3">
            <Info className="h-4 w-4 text-info" />
            <div className="flex-1 min-w-0">
              <AlertTitle>{t("noBoardConfigured")}</AlertTitle>
              <AlertDescription>{t("noBoardDescription")}</AlertDescription>
            </div>
            <Button
              variant="brand"
              size="sm"
              onClick={triggerWizard}
              className="w-fit btn-lift shrink-0 self-center sm:self-center"
            >
              {t("runSetupWizard")}
            </Button>
          </Alert>
        </div>
      )}

      <SilenceImminentBanner />

      <div className="animate-card-fade-in">
        <ActivePageDisplay />
      </div>
    </PageLayout>
  );
}
