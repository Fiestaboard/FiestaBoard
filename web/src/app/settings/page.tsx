"use client";

import { DisplaySettings } from "@/components/settings/display-settings";
import { TransitionSettings } from "@/components/settings/transition-settings";
import { DebugSettings } from "@/components/settings/debug-settings";
import { SystemUpdate } from "@/components/settings/system-update";
import { SystemControls } from "@/components/settings/system-controls";
import { MqttSettingsCard } from "@/components/settings/mqtt-settings";
import { LocationSettingsCard } from "@/components/settings/location-settings";
import { GeneralSettings } from "@/components/general-settings";
import { useWizard } from "@/components/wizard-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Wand2, Settings } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { PageLayout } from "@/components/page-layout";
import { useTranslations } from "next-intl";

export default function SettingsPage() {
  const { triggerWizard } = useWizard();
  const t = useTranslations("settings");

  return (
    <PageLayout>
      <PageHeader icon={Settings} title={t("title")} description={t("description")} />
      <div className="space-y-6">
        <div className="animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <SystemUpdate />
        </div>

        <div className="animate-card-fade-in" style={{ animationDelay: "100ms" }}>
          <DisplaySettings />
        </div>

        <div className="animate-card-fade-in" style={{ animationDelay: "200ms" }}>
          <TransitionSettings />
        </div>

        <div className="animate-card-fade-in" style={{ animationDelay: "300ms" }}>
          <GeneralSettings />
        </div>

        <div className="animate-card-fade-in" style={{ animationDelay: "400ms" }}>
          <MqttSettingsCard />
        </div>

        <div className="animate-card-fade-in" style={{ animationDelay: "440ms" }}>
          <LocationSettingsCard />
        </div>

        <div className="animate-card-fade-in overflow-hidden" style={{ animationDelay: "480ms" }}>
          <DebugSettings />
        </div>

        <div className="animate-card-fade-in" style={{ animationDelay: "520ms" }}>
          <SystemControls />
        </div>

        <Card className="animate-card-fade-in" style={{ animationDelay: "560ms" }}>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Wand2 className="h-4 w-4" />
              {t("setupWizardTitle")}
            </CardTitle>
            <CardDescription>
              {t("setupWizardDescription")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="brand" onClick={triggerWizard} className="gap-2 btn-lift">
              <Wand2 className="h-4 w-4" />
              {t("runSetupWizard")}
            </Button>
          </CardContent>
        </Card>
      </div>
    </PageLayout>
  );
}
