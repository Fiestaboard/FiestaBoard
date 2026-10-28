import {
  Box,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Grid,
  PageCard,
  PageHeader,
  PageLayout,
  PageSection,
  Skeleton,
  Stack,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import { Cog, Settings, ShieldCheck, Sparkles, User, Wand2, Wifi, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo } from "react";
import { Navigate } from "react-router";

import { AccountSection } from "@/components/account-section";
import { useCurrentBoard } from "@/components/current-board-context";
import { AccessibilitySettings } from "@/components/settings/accessibility-settings";
import { AiSettings } from "@/components/settings/ai-settings";
import { AnimationSettings } from "@/components/settings/animation-settings";
import { AppearanceSettings } from "@/components/settings/appearance-settings";
import { AutoUpdateIntervalCard } from "@/components/settings/auto-update-interval";
import { BackupSettings } from "@/components/settings/backup-settings";
import { DebugSettings } from "@/components/settings/debug-settings";
import { InstanceNameCard } from "@/components/settings/instance-name";
import { LanguageSettingsCard } from "@/components/settings/language-settings";
import { LocationSettingsCard } from "@/components/settings/location-settings";
import { McpSettings } from "@/components/settings/mcp-settings";
import { MqttSettingsCard } from "@/components/settings/mqtt-settings";
import { NetworkSettings } from "@/components/settings/network-settings";
import { ReleaseChannelCard } from "@/components/settings/release-channel";
import { SystemControls } from "@/components/settings/system-controls";
import { SystemUpdate } from "@/components/settings/system-update";
import { TimeAndDateCard } from "@/components/settings/time-and-date";
import { useWizard } from "@/components/wizard-provider";
import { useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

type SectionId = "general" | "account" | "network" | "ai" | "system" | "advanced";

/**
 * The tab boards and FiestaPanels used to live in. Displays have their own
 * section now (plan D21); an old `?section=hardware` link lands there.
 */
const LEGACY_HARDWARE_SECTION = "hardware";

/**
 * Tabs that were renamed, mapped to the tab that now holds their cards, so a
 * bookmark or an old docs link still opens the right place. Integrations became AI (its MQTT card moved to General and its
 * plugin-update card to the Integrations page, but AI is what most of its
 * links were for — the OAuth return among them).
 */
const LEGACY_SECTIONS: Readonly<Record<string, SectionId>> = {
  integrations: "ai",
};

const SECTION_IDS: readonly SectionId[] = ["general", "account", "network", "ai", "system", "advanced"] as const;

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
  const { boards, currentBoardId, isLoading: boardsLoading } = useCurrentBoard();

  // Account tab is visible when:
  //   - auth is on AND the user is signed in (account management UI), or
  //   - auth is currently disabled (nudge card encouraging them to turn
  //     it back on)
  // It's hidden when auth is on but the user isn't signed in (they
  // shouldn't even be on this page in that case — middleware will
  // bounce them to /login).
  const { data: authStatus } = useQuery({
    queryKey: ["auth-status"],
    queryFn: api.getAuthStatus,
    staleTime: 30_000,
    retry: false,
  });
  const showAccount = (!!authStatus?.enabled && !!authStatus.authenticated) || authStatus?.mode === "disabled";

  // The Network tab is gated on the backend capability probe — it only
  // appears on the FiestaPi (or any deployment where the API container
  // has nmcli + a D-Bus mount). On vanilla Docker installs this returns
  // available: false and we never render the tab.
  const { data: wifiCapability } = useQuery({
    queryKey: ["wifi-capability"],
    queryFn: api.getWifiCapability,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const showNetwork = !!wifiCapability?.available;

  const requested = searchParams.get("section");
  const resolved = requested !== null && requested in LEGACY_SECTIONS ? LEGACY_SECTIONS[requested] : requested;
  let activeSection: SectionId = isSectionId(resolved) ? resolved : DEFAULT_SECTION;
  // If the URL asks for a tab that isn't currently visible (e.g.
  // ?section=account when auth is off), fall back to the default
  // instead of rendering an empty tab body.
  if (activeSection === "account" && !showAccount) {
    activeSection = DEFAULT_SECTION;
  }
  if (activeSection === "network" && !showNetwork) {
    activeSection = DEFAULT_SECTION;
  }

  // Scroll to a hash anchor when the active tab
  // mounts, and pulse the target card so the user can see what they navigated
  // to. Legacy board scheduling links are redirected below.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash.replace(/^#/, "");
    if (!hash) return;
    const timer = setTimeout(() => {
      const el = document.getElementById(hash);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      el.classList.add("settings-anchor-highlight");
      setTimeout(() => el.classList.remove("settings-anchor-highlight"), 2200);
    }, 120);
    return () => clearTimeout(timer);
  }, [activeSection]);

  const handleSectionChange = useCallback(
    (id: string) => {
      if (!isSectionId(id)) return;
      const params = new URLSearchParams(searchParams.toString());
      params.set("section", id);
      router.replace(`/settings?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  const sections = useMemo<SectionMeta[]>(() => {
    const all: SectionMeta[] = [
      { id: "general", label: t("sectionGeneral"), icon: User },
      { id: "account", label: t("sectionAccount"), icon: ShieldCheck },
      { id: "network", label: t("sectionNetwork"), icon: Wifi },
      { id: "ai", label: t("sectionAi"), icon: Sparkles },
      { id: "system", label: t("sectionSystem"), icon: Cog },
      { id: "advanced", label: t("sectionAdvanced"), icon: Wrench },
    ];
    return all.filter((s) => {
      if (s.id === "account") return showAccount;
      if (s.id === "network") return showNetwork;
      return true;
    });
  }, [t, showAccount, showNetwork]);

  // Settings → Hardware moved to Displays (plan D21): keep old links working.
  if (requested === LEGACY_HARDWARE_SECTION) {
    const hash = typeof window === "undefined" ? "" : window.location.hash;
    return <Navigate to={`/displays${hash}`} replace />;
  }

  // Timing and schedule behavior belong to a display. Preserve old bookmarks
  // without exposing controls that could accidentally edit another board.
  if (requested === "scheduling" || requested === "behavior") {
    if (boardsLoading) return <Skeleton className="h-40 w-full" />;
    const explicitId = searchParams.get("board_id");
    const board = boards.find((candidate) => candidate.id === (explicitId ?? currentBoardId));
    const hash = typeof window === "undefined" ? "" : window.location.hash;
    return (
      <Navigate
        to={board ? `/displays/${encodeURIComponent(board.id)}?section=playback${hash}` : "/displays"}
        replace
      />
    );
  }

  return (
    <PageLayout>
      {/* Tabs wraps the card so the tab strip and the panels are both blocks
          inside it — same reason as the Integrations route. */}
      <Tabs value={activeSection} onValueChange={handleSectionChange}>
        <PageCard>
          <PageHeader icon={Settings} title={t("title")} description={t("description")} />

          {/* Unwrapped on purpose: SystemUpdate brings its own PageSection
              when it has something to announce and renders nothing when it
              does not. A section here would draw an empty band on every
              up-to-date install — see the note on its return. */}
          <SystemUpdate />

          <PageSection>
            <Box className="-mx-6 overflow-x-auto px-6">
              <TabsList className="w-fit h-auto p-1">
                {sections.map(({ id, label, icon: Icon }) => (
                  <TabsTrigger key={id} value={id} className="gap-1.5 px-3 py-1.5 data-[state=active]:shadow-sm">
                    <Icon className="h-4 w-4 flex-shrink-0" />
                    {/* Inherits size/weight/color from TabsTrigger's data-active state — Text's fixed
                    tone/weight defaults would break the active/inactive styling, so this stays raw. */}
                    {/* eslint-disable-next-line react/forbid-elements -- inherit-only span; TabsTrigger drives its active/inactive size/weight/color and Text's fixed defaults would break that */}
                    <span className="whitespace-nowrap">{label}</span>
                  </TabsTrigger>
                ))}
              </TabsList>
            </Box>
          </PageSection>

          <TabsContent value="general" className="mt-0">
            <InstanceNameCard />
            <PageSection title={t("groupAppearance")}>
              <Grid
                cols="1"
                lg="2"
                gap="6"
                className="[&>[data-slot=page-section]]:border-0 [&>[data-slot=page-section]]:p-0"
              >
                <AppearanceSettings />
                <AccessibilitySettings />
              </Grid>
            </PageSection>
            <AnimationSettings />
            <PageSection title={t("groupRegional")}>
              <Grid
                cols="1"
                lg="2"
                gap="6"
                className="[&>[data-slot=page-section]]:border-0 [&>[data-slot=page-section]]:p-0"
              >
                <Stack gap="6" className="[&>[data-slot=page-section]]:border-0 [&>[data-slot=page-section]]:p-0">
                  <LanguageSettingsCard />
                  <LocationSettingsCard />
                </Stack>
                <TimeAndDateCard />
              </Grid>
            </PageSection>
            <PageSection
              title={t("groupConnections")}
              contentClassName="[&>[data-slot=page-section]]:border-0 [&>[data-slot=page-section]]:p-0"
            >
              <MqttSettingsCard />
            </PageSection>
          </TabsContent>

          {showAccount && (
            <TabsContent value="account" className="mt-0">
              <AccountSection />
            </TabsContent>
          )}

          {showNetwork && (
            <TabsContent value="network" className="mt-0">
              <NetworkSettings />
            </TabsContent>
          )}

          <TabsContent value="ai" className="mt-0">
            <AiSettings />
            <McpSettings />
          </TabsContent>

          <TabsContent value="system" className="mt-0">
            <SystemControls />
            <AutoUpdateIntervalCard />
            <ReleaseChannelCard />
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
          </TabsContent>

          <TabsContent value="advanced" className="mt-0">
            <DebugSettings />
          </TabsContent>
        </PageCard>
      </Tabs>
    </PageLayout>
  );
}
