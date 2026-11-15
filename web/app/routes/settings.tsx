import {
  Box,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FiestaIcon,
  Flex,
  Grid,
  Heading,
  ListItem,
  ListRow,
  ListRowGroup,
  PageCard,
  PageHeader,
  PageLayout,
  PageSection,
  Skeleton,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Info, Settings, Wand2 } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { Navigate } from "react-router";

import { AboutDialog } from "@/components/about-dialog";
import { AccountSection } from "@/components/account-section";
import { useCurrentBoard } from "@/components/current-board-context";
import { HubLine } from "@/components/hub-line";
import { HttpsRequiredBanner } from "@/components/pwa/https-required-banner";
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
import Link from "@/components/smart-link";
import { ViewTransitionLink } from "@/components/view-transition-link";
import { useWizard } from "@/components/wizard-provider";
import { RAIL_BREAKPOINT, useBelowRail } from "@/hooks/use-below-rail";
import { useHubIdentity } from "@/hooks/use-hub-identity";
import { useParams, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import {
  legacySettingsTarget,
  resolveSettingsSection,
  SETTINGS_SECTIONS,
  type SettingsGroup,
  settingsSectionHref,
  type SettingsSectionId,
} from "@/lib/settings-sections";

/**
 * The tab boards and FiestaPanels used to live in. Displays have their own
 * section now (plan D21); an old `?section=hardware` link lands there.
 */
const LEGACY_HARDWARE_SECTION = "hardware";

/**
 * Settings, as a list-detail (slice 2.1, WEB-01; Figma 07e §1): a hub card,
 * then the reader's own settings ("You") and the hub's ("Hub · <name>", the
 * Settings › Hub group), each section a route of its own,
 * `/settings/:section`. From 768px the list and the open section sit side by
 * side; below it the list is `/settings` and a section is its own screen
 * with a way back. It replaces six horizontal tabs that overflowed at 375px.
 */
export default function SettingsPage() {
  const t = useTranslations("settings");
  const tHub = useTranslations("settings.hub");
  const { section: sectionParam } = useParams<{ section?: string }>();
  const searchParams = useSearchParams();
  const { boards, currentBoardId, isLoading: boardsLoading } = useCurrentBoard();
  const belowRail = useBelowRail();
  const hub = useHubIdentity();
  const hubName = hub.name ?? tHub("hubFallbackName");

  // Account is listed when auth is on and you are signed in (account
  // management), or when auth is off (a card nudging you to turn it back on).
  // When auth is on and you are signed out, the middleware has already sent
  // you to /login.
  const { data: authStatus } = useQuery({
    queryKey: ["auth-status"],
    queryFn: api.getAuthStatus,
    staleTime: 30_000,
    retry: false,
  });
  // Until auth status answers, Account counts as visible: a deep link to it
  // must not flash Appearance first (or bounce to the index) while it loads.
  const showAccount =
    authStatus === undefined || (!!authStatus.enabled && !!authStatus.authenticated) || authStatus.mode === "disabled";
  const username = authStatus?.enabled && authStatus.authenticated ? (authStatus.username ?? null) : null;

  const visible = useMemo<SettingsSectionId[]>(
    () => SETTINGS_SECTIONS.map((s) => s.id).filter((id) => id !== "account" || showAccount),
    [showAccount],
  );
  const active = resolveSettingsSection(sectionParam, visible);

  // Scroll to a hash anchor once the section mounts, and pulse the target
  // card so the reader sees what they were sent to.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash.replace(/^#/, "");
    if (!hash) return;
    const timer = setTimeout(() => {
      const targetId = hash === "time-and-date" || hash === "timezone" ? "time" : hash;
      const el = document.getElementById(targetId);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      el.classList.add("settings-anchor-highlight");
      setTimeout(() => el.classList.remove("settings-anchor-highlight"), 2200);
    }, 120);
    return () => clearTimeout(timer);
  }, [active]);

  const requested = searchParams.get("section");
  const hash = typeof window === "undefined" ? "" : window.location.hash;

  // Settings → Hardware moved to Displays (plan D21): keep old links working.
  if (requested === LEGACY_HARDWARE_SECTION) {
    return <Navigate to={`/displays${hash}`} replace />;
  }

  // Timing and schedule behavior belong to a display. Preserve old bookmarks
  // without exposing controls that could accidentally edit another board.
  if (requested === "scheduling" || requested === "behavior") {
    if (boardsLoading) return <Skeleton className="h-40 w-full" />;
    const explicitId = searchParams.get("board_id");
    const board = boards.find((candidate) => candidate.id === (explicitId ?? currentBoardId));
    return (
      <Navigate
        to={board ? `/displays/${encodeURIComponent(board.id)}?section=playback${hash}` : "/displays"}
        replace
      />
    );
  }

  // The old tabs (`?section=general`, `?section=ai`, …) become paths. Every
  // other query parameter rides along: the AI provider's OAuth return is one.
  const legacy = legacySettingsTarget(requested, hash);
  if (legacy) {
    const rest = new URLSearchParams(searchParams.toString());
    rest.delete("section");
    const query = rest.toString();
    return <Navigate to={`${settingsSectionHref(legacy)}${query ? `?${query}` : ""}${hash}`} replace />;
  }

  // A path that names no section the reader can see goes to the index
  // rather than showing some other section under a URL that names nothing.
  if (active === null) {
    return <Navigate to="/settings" replace />;
  }

  // Below the rail one pane at a time: the list at /settings, a section at
  // /settings/:section. From the rail on, both.
  const showList = !belowRail || !sectionParam;
  const showDetail = !belowRail || !!sectionParam;

  const rowMeta: Partial<Record<SettingsSectionId, { description?: string }>> = {
    account: username ? { description: username } : undefined,
  };

  const list = (
    <Stack gap="4" data-slot="settings-index">
      <Card data-slot="settings-hub-card" className="py-4">
        <CardContent className="px-4">
          <Flex align="center" gap="3">
            <FiestaIcon size={32} className="shrink-0" />
            <Stack gap="0.5" className="min-w-0">
              <Text weight="semibold" className="truncate">
                {hubName}
              </Text>
              <HubLine hub={hub} />
            </Stack>
          </Flex>
        </CardContent>
      </Card>
      {(["you", "hub"] as SettingsGroup[]).map((group) => (
        <SettingsGroupList
          key={group}
          label={group === "you" ? tHub("you") : tHub("hubGroup", { name: hubName })}
          sections={SETTINGS_SECTIONS.filter((s) => s.group === group && visible.includes(s.id))}
          active={belowRail ? null : active}
          title={(id) => tHub(`sections.${id}.title`)}
          meta={rowMeta}
        />
      ))}
    </Stack>
  );

  const detailTitleId = `settings-${active}-title`;
  const detail = (
    <Stack gap="4" aria-labelledby={detailTitleId} role="region" data-slot="settings-detail">
      <Stack gap="1">
        <Heading level={belowRail ? 1 : 2} size={belowRail ? "2xl" : "lg"} id={detailTitleId}>
          {tHub(`sections.${active}.title`)}
        </Heading>
        <Text size="sm" tone="muted">
          {tHub(`sections.${active}.description`, { name: hubName })}
        </Text>
      </Stack>
      <PageCard>
        <SettingsSectionBody section={active} />
      </PageCard>
    </Stack>
  );

  return (
    <PageLayout railBreakpoint={RAIL_BREAKPOINT}>
      {belowRail && sectionParam ? (
        <Box className="mb-4">
          <ViewTransitionLink
            href="/settings"
            className="inline-flex min-h-11 items-center gap-1 text-sm font-medium text-brand focus-ring rounded-md"
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
            {t("title")}
          </ViewTransitionLink>
        </Box>
      ) : (
        <PageHeader icon={Settings} title={t("title")} description={t("description")} />
      )}

      {/* Unwrapped on purpose: SystemUpdate brings its own section when it
          has something to announce and renders nothing when it does not. */}
      <SystemUpdate />
      {/* 2.8: Notifications will own this once slice 2.13 supplies that section. */}
      <HttpsRequiredBanner className="mt-4" />

      {/* The columns follow the room the page actually has, not the
          viewport: FiestaBot's drawer takes 396px from 1024px up, which at
          1100px leaves no room for a detail column beside the list. Side by
          side from a 36rem content box (280px list), 360px list from 56rem;
          below that the list and the open section stack. */}
      <Box className="@container mt-6" data-slot="settings-columns">
        <Grid
          cols="1"
          gap="6"
          className="md:@xl:grid-cols-[minmax(0,17.5rem)_minmax(0,1fr)] md:@4xl:grid-cols-[minmax(0,22.5rem)_minmax(0,1fr)] md:@xl:items-start"
        >
          {showList && list}
          {showDetail && detail}
        </Grid>
      </Box>
    </PageLayout>
  );
}

interface SettingsGroupListProps {
  label: string;
  sections: readonly (typeof SETTINGS_SECTIONS)[number][];
  active: SettingsSectionId | null;
  title: (id: SettingsSectionId) => string;
  meta: Partial<Record<SettingsSectionId, { description?: string }>>;
}

/** One group of the index: its label, then a row per section. */
function SettingsGroupList({ label, sections, active, title, meta }: SettingsGroupListProps) {
  const labelId = useId();
  if (sections.length === 0) return null;
  return (
    <Stack gap="2">
      <Text id={labelId} size="xs" tone="muted" weight="medium" className="px-1 uppercase">
        {label}
      </Text>
      <ListRowGroup aria-labelledby={labelId}>
        {sections.map(({ id, icon: Icon }) => {
          const current = active === id;
          return (
            <ListItem key={id}>
              <ListRow
                // The kit's selected state (FiestaUI 1.8e): 07e's inset pill
                // and aria-current="page".
                selected={current}
                render={<Link href={settingsSectionHref(id)} />}
                leading={<Icon className="size-4 text-foreground" aria-hidden="true" />}
                title={title(id)}
                description={meta[id]?.description}
                trailing={<ChevronRight className="size-4" aria-hidden="true" />}
              />
            </ListItem>
          );
        })}
      </ListRowGroup>
    </Stack>
  );
}

/**
 * The cards each section holds: the cards the six old tabs held, regrouped
 * by whose they are. The sections' own 07e redesigns are slice 2.14's.
 */
function SettingsSectionBody({ section }: { section: SettingsSectionId }) {
  const t = useTranslations("settings");
  const tMenu = useTranslations("settingsMenu");
  const { triggerWizard } = useWizard();
  const [aboutOpen, setAboutOpen] = useState(false);

  // The Wi-Fi card needs nmcli and a D-Bus mount on the hub (a FiestaPi);
  // elsewhere the capability probe says no and Network is MQTT alone.
  const { data: wifiCapability } = useQuery({
    queryKey: ["wifi-capability"],
    queryFn: api.getWifiCapability,
    staleTime: 5 * 60_000,
    retry: false,
    enabled: section === "network",
  });

  switch (section) {
    case "account":
      return <AccountSection />;
    case "appearance":
      return (
        <>
          <AppearanceSettings />
          <AnimationSettings />
        </>
      );
    case "accessibility":
      return <AccessibilitySettings />;
    case "network":
      return (
        <>
          {wifiCapability?.available && <NetworkSettings />}
          <MqttSettingsCard />
        </>
      );
    case "ai-provider":
      return (
        <>
          <AiSettings />
          <McpSettings />
        </>
      );
    case "system":
      return (
        <>
          <InstanceNameCard />
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
          <DebugSettings />
          {/* The About box's only home on a phone (the rail keeps it in the
              account menu too). Same dialog, not a second About card. */}
          <PageSection>
            <Button variant="outline" onClick={() => setAboutOpen(true)} className="gap-2">
              <Info className="h-4 w-4" aria-hidden="true" />
              {tMenu("about")}
            </Button>
            <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
          </PageSection>
        </>
      );
    case "language-time":
      return (
        <>
          <LanguageSettingsCard />
          <LocationSettingsCard />
          <TimeAndDateCard />
        </>
      );
  }
}
