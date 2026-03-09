"use client";

import { useEffect, useState } from "react";
import { ActivePageDisplay } from "@/components/active-page-display";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Info, Home as HomeIcon } from "lucide-react";
import { getSetupStatus } from "@/lib/setup-detection";
import { useWizard } from "@/components/wizard-provider";
import { useTranslations } from "next-intl";

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
    <div className="min-h-screen bg-background overflow-x-hidden relative">
      <div className="container relative z-10 mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
        <div className="mb-6 animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <h1 className="page-title flex items-center gap-3">
            <HomeIcon className="h-7 w-7 text-brand-emphasis" />
            {t("title")}
          </h1>
          <p className="page-description">
            {t("description")}
          </p>
        </div>

        {boardNotConfigured && (
          <div className="mb-6">
            <Alert className="border-info/50 bg-info/10">
              <Info className="h-4 w-4 text-info" />
              <AlertTitle>{t("noBoardConfigured")}</AlertTitle>
              <AlertDescription className="flex flex-col sm:flex-row sm:items-center gap-2">
                <span>
                  {t("noBoardDescription")}
                </span>
                <Button variant="brand" size="sm" onClick={triggerWizard} className="w-fit btn-lift">
                  {t("runSetupWizard")}
                </Button>
              </AlertDescription>
            </Alert>
          </div>
        )}

        <div className="animate-card-fade-in">
          <ActivePageDisplay />
        </div>
      </div>
    </div>
  );
}
