"use client";

import { useCallback, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  Cog,
  MonitorCog,
  Plug,
  Settings,
  ShieldCheck,
  User,
  Wand2,
  Waves,
  Wrench,
} from "lucide-react";

import { api } from "@/lib/api";

import { PageHeader } from "@/components/page-header";
import { PageLayout } from "@/components/page-layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { AboutCard } from "@/components/settings/about-card";
import { AccessibilitySettings } from "@/components/settings/accessibility-settings";
import { AccountSection } from "@/components/account-section";
import { AiSettings } from "@/components/settings/ai-settings";
import { AppearanceSettings } from "@/components/settings/appearance-settings";
import { AutoUpdateIntervalCard } from "@/components/settings/auto-update-interval";
import { BackupSettings } from "@/components/settings/backup-settings";
import { BetaSettings } from "@/components/settings/beta-settings";
import { DebugSettings } from "@/components/settings/debug-settings";
import { DisplaySettings } from "@/components/settings/display-settings";
import { InstanceNameCard } from "@/components/settings/instance-name";
import { LanguageSettingsCard } from "@/components/settings/language-settings";
import { LocationSettingsCard } from "@/components/settings/location-settings";
import { MqttSettingsCard } from "@/components/settings/mqtt-settings";
import { PluginSettingsCard } from "@/components/settings/plugin-settings";
import { SilenceSchedule } from "@/components/settings/silence-schedule";
import { SystemControls } from "@/components/settings/system-controls";
import { SystemUpdate } from "@/components/settings/system-update";
import { TimeAndDateCard } from "@/components/settings/time-and-date";
import { TransitionSettings } from "@/components/settings/transition-settings";
import { UpdateIntervals } from "@/components/settings/update-intervals";
import { useWizard } from "@/components/wizard-provider";

type SectionId =
  | "general"
  | "account"
  | "hardware"
  | "behavior"
  | "integrations"
  | "system"
  | "advanced";

const SECTION_IDS: readonly SectionId[] = [
  "general",
  "account",
  "hardware",
  "behavior",
  "integrations",
  "system",
  "advanced",
] as const;

const DEFAULT_SECTION: SectionId = "general";

function isSectionId(value: string | null): value is SectionId {
  return value !== null && (SECTION_IDS as readonly string[]).includes(value);
}

interface SectionMeta {
  id: SectionId;
  label: string;
  icon: LucideIcon;
}

export default function SettingsPage() {
  const t = useTranslations("settings");
  const router = useRouter();
  const searchParams = useSearchParams();
  const { triggerWizard } = useWizard();

  // The Account tab is only meaningful when auth is on — otherwise
  // there's nothing to manage. Hide the tab entirely in that case.
  const { data: authStatus } = useQuery({
    queryKey: ["auth-status"],
    queryFn: api.getAuthStatus,
    staleTime: 30_000,
    retry: false,
  });
  const showAccount = !!authStatus?.enabled && !!authStatus.authenticated;

  const requested = searchParams.get("section");
  let activeSection: SectionId = isSectionId(requested)
    ? requested
    : DEFAULT_SECTION;
  // If the URL asks for a tab that isn't currently visible (e.g.
  // ?section=account when auth is off), fall back to the default
  // instead of rendering an empty tab body.
  if (activeSection === "account" && !showAccount) {
    activeSection = DEFAULT_SECTION;
  }

  const handleSectionChange = useCallback(
    (id: string) => {
      if (!isSectionId(id)) return;
      const params = new URLSearchParams(searchParams.toString());
      params.set("section", id);
      router.replace(`/settings?${params.toString()}`, { scroll: false });
    },
    [router, searchParams]
  );

  const sections = useMemo<SectionMeta[]>(
    () => {
      const all: SectionMeta[] = [
        { id: "general", label: t("sectionGeneral"), icon: User },
        { id: "account", label: t("sectionAccount"), icon: ShieldCheck },
        { id: "hardware", label: t("sectionHardware"), icon: MonitorCog },
        { id: "behavior", label: t("sectionBehavior"), icon: Waves },
        { id: "integrations", label: t("sectionIntegrations"), icon: Plug },
        { id: "system", label: t("sectionSystem"), icon: Cog },
        { id: "advanced", label: t("sectionAdvanced"), icon: Wrench },
      ];
      return showAccount ? all : all.filter((s) => s.id !== "account");
    },
    [t, showAccount]
  );

  return (
    <PageLayout>
      <PageHeader icon={Settings} title={t("title")} description={t("description")} />

      <div className="mb-5">
        <SystemUpdate />
      </div>

      <Tabs value={activeSection} onValueChange={handleSectionChange}>
        <div className="mb-5 -mx-3 sm:-mx-4 md:mx-0 overflow-x-auto px-3 sm:px-4 md:px-0">
          <TabsList className="w-fit h-auto p-1">
            {sections.map(({ id, label, icon: Icon }) => (
              <TabsTrigger
                key={id}
                value={id}
                className="gap-1.5 px-3 py-1.5 data-[state=active]:shadow-sm"
              >
                <Icon className="h-4 w-4 flex-shrink-0" />
                <span className="whitespace-nowrap">{label}</span>
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <TabsContent value="general" className="mt-0 space-y-6">
          <InstanceNameCard />
          <AppearanceSettings />
          <LanguageSettingsCard />
          <TimeAndDateCard />
          <LocationSettingsCard />
          <AccessibilitySettings />
        </TabsContent>

        {showAccount && (
          <TabsContent value="account" className="mt-0 space-y-6">
            <AccountSection />
          </TabsContent>
        )}

        <TabsContent value="hardware" className="mt-0 space-y-6">
          <DisplaySettings />
        </TabsContent>

        <TabsContent value="behavior" className="mt-0 space-y-6">
          <TransitionSettings />
          <UpdateIntervals />
          <SilenceSchedule />
        </TabsContent>

        <TabsContent value="integrations" className="mt-0 space-y-6">
          <AiSettings />
          <MqttSettingsCard />
          <PluginSettingsCard />
        </TabsContent>

        <TabsContent value="system" className="mt-0 space-y-6">
          <SystemControls />
          <AutoUpdateIntervalCard />
          <BackupSettings />
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Wand2 className="h-4 w-4" />
                {t("setupWizardTitle")}
              </CardTitle>
              <CardDescription>{t("setupWizardDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="brand" onClick={triggerWizard} className="gap-2 btn-lift">
                <Wand2 className="h-4 w-4" />
                {t("runSetupWizard")}
              </Button>
            </CardContent>
          </Card>
          <AboutCard />
        </TabsContent>

        <TabsContent value="advanced" className="mt-0 space-y-6">
          <DebugSettings />
          <BetaSettings />
        </TabsContent>
      </Tabs>
    </PageLayout>
  );
}
