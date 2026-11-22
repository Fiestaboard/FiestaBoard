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
  PageHeader,
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
import { FlatPage } from "@/components/section-shell";
import { AccessibilitySettings } from "@/components/settings/accessibility-settings";
import { AiSettings } from "@/components/settings/ai-settings";
import { AnimationSettings } from "@/components/settings/animation-settings";
import { AppearanceSettings } from "@/components/settings/appearance-settings";
import { AutoUpdateIntervalCard } from "@/components/settings/auto-update-interval";
import { BackupSettings } from "@/components/settings/backup-settings";
import { DebugSettings } from "@/components/settings/debug-settings";
import { FiestaBotSettings } from "@/components/settings/fiestabot-settings";
import { InstanceNameCard } from "@/components/settings/instance-name";
import { LanguageSettingsCard } from "@/components/settings/language-settings";
import { LocationSettingsCard } from "@/components/settings/location-settings";
import { McpSettings } from "@/components/settings/mcp-settings";
import { MqttSettingsCard } from "@/components/settings/mqtt-settings";
import { NetworkAddresses } from "@/components/settings/network-addresses";
import { NetworkSettings } from "@/components/settings/network-settings";
import { NotificationSettings } from "@/components/settings/notification-settings";
import { ReleaseChannelCard } from "@/components/settings/release-channel";
import { SettingsPanel } from "@/components/settings/settings-panel";
import { SystemControls } from "@/components/settings/system-controls";
import { SystemUpdate } from "@/components/settings/system-update";
import { TimeAndDateCard } from "@/components/settings/time-and-date";
import Link from "@/components/smart-link";
import { ViewTransitionLink } from "@/components/view-transition-link";
import { isUntouchedPlaceholder } from "@/components/wizard/default-board";
import { useWizard } from "@/components/wizard-provider";
import { useBelowRail } from "@/hooks/use-below-rail";
import { useHubIdentity } from "@/hooks/use-hub-identity";
import { useParams, useSearchParams } from "@/hooks/use-router";
import { useTheme } from "@/hooks/use-theme";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { pushApi } from "@/lib/api/push";
import { sessionsApi } from "@/lib/api/sessions";
import { INSET_ROW, INSET_ROW_GROUP } from "@/lib/list-row-inset";
import { browserHostname } from "@/lib/network-hint";
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
  const rowMeta = useRowMeta({
    username,
    sessions: !!authStatus?.session_management_supported && !!username,
    // Only while the list is on screen (always from the rail up).
    enabled: !belowRail || !sectionParam,
  });

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
      {/* 07e `320:8881`: Heading/2xl on a phone (xl beside the list), and
          under it only the hub it belongs to (Text/xs) — BB-FC-1. */}
      <Stack gap="1">
        <Heading level={belowRail ? 1 : 2} size={belowRail ? "2xl" : "xl"} id={detailTitleId}>
          {tHub(`sections.${active}.title`)}
        </Heading>
        <Text size="xs" tone="muted" data-slot="settings-detail-meta">
          {[hubName, browserHostname()].filter(Boolean).join(" · ")}
        </Text>
      </Stack>
      {/* Account's cards and its Signed-in devices sit straight on the page
          (07e `322:31855`), not inside a PageCard that has no padding of its
          own on a phone (BB-C-24). */}
      {active === "notifications" ? (
        <NotificationSettings />
      ) : (
        <Stack gap="4">
          <SettingsSectionBody section={active} />
        </Stack>
      )}
    </Stack>
  );

  return (
    <FlatPage>
      {belowRail && !sectionParam ? (
        <PhoneIndexHeader title={t("title")} />
      ) : belowRail && sectionParam ? (
        <Box>
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

      {/* The columns follow the room the page actually has, not the
          viewport: FiestaBot's drawer takes 396px from 1024px up, which at
          1100px leaves no room for a detail column beside the list. Side by
          side from a 36rem content box (280px list), 360px list from 56rem;
          below that the list and the open section stack. */}
      <Box className="@container" data-slot="settings-columns">
        <Grid
          cols="1"
          gap="6"
          className="md:@xl:grid-cols-[minmax(0,17.5rem)_minmax(0,1fr)] md:@4xl:grid-cols-[minmax(0,23.75rem)_minmax(0,1fr)] md:@xl:items-start"
        >
          {showList && list}
          {showDetail && detail}
        </Grid>
      </Box>
    </FlatPage>
  );
}

type RowMeta = Partial<Record<SettingsSectionId, { description?: string; meta?: string }>>;

/**
 * The phone index head (07e `320:7936`): "‹ More", then a plain, left-aligned
 * "Settings". On a phone Settings is reached from the More drawer, which is
 * the shell's (FiestaUI Sidebar `bottom-nav`); it has no API to open it, so
 * the back link presses the shell's own More tab, found by its kit slot.
 */
function PhoneIndexHeader({ title }: { title: string }) {
  const tNav = useTranslations("navigation");
  return (
    <Stack gap="4" className="mb-2" data-slot="settings-phone-header">
      {/* The section screens' "‹ Settings" link, as a button: it opens a drawer. */}
      <button
        type="button"
        className="inline-flex min-h-11 items-center gap-1 self-start rounded-md text-sm font-medium text-brand focus-ring"
        onClick={() => document.querySelector<HTMLButtonElement>('[data-slot="sidebar-bottom-nav-more"]')?.click()}
      >
        <ChevronLeft className="size-4" aria-hidden="true" />
        {tNav("more")}
      </button>
      <Heading level={1} size="3xl">
        {title}
      </Heading>
    </Stack>
  );
}

/**
 * The value each index row reads with its title (07e `320:7936`), from what
 * the hub already reports. A row shows nothing when there is no honest value:
 * Notifications reports on/off, not 07e's per-category count; Network has no
 * value off a FiestaPi's Wi-Fi.
 */
function useRowMeta({
  username,
  sessions,
  enabled,
}: {
  username: string | null;
  sessions: boolean;
  enabled: boolean;
}): RowMeta {
  const tHub = useTranslations("settings.hub");
  const tCommon = useTranslations("common");
  const tProfile = useTranslations("profile");
  const { theme } = useTheme();
  const signedIn = useQuery({
    queryKey: ["auth-sessions"],
    queryFn: sessionsApi.listSessions,
    staleTime: 30_000,
    retry: false,
    enabled: enabled && sessions,
  });
  // The Notifications screen's own cache key.
  const push = useQuery({
    queryKey: ["push-status"],
    queryFn: pushApi.getStatus,
    staleTime: 15_000,
    retry: false,
    enabled: enabled && !!username,
  });
  const ai = useQuery({ queryKey: ["ai-settings"], queryFn: api.getAiSettings, retry: false, enabled });
  const wifiCapability = useQuery({
    queryKey: ["wifi-capability"],
    queryFn: api.getWifiCapability,
    staleTime: 5 * 60_000,
    retry: false,
    enabled,
  });
  const wifi = useQuery({
    queryKey: ["wifi", "status"],
    queryFn: api.getWifiStatus,
    retry: false,
    enabled: enabled && !!wifiCapability.data?.available,
  });

  const count = signedIn.data?.sessions.length;
  const provider = ai.data?.enabled
    ? (ai.data.providers.find((p) => p.id === ai.data?.default_provider_id) ?? ai.data.providers[0])
    : undefined;
  const themes = { light: tProfile("lightMode"), dark: tProfile("darkMode"), system: tProfile("systemMode") };
  return {
    account: username
      ? { description: count === undefined ? username : tHub("accountMeta", { name: username, count }) }
      : undefined,
    notifications: push.data
      ? {
          meta:
            push.data.user_enabled && push.data.device_enabled && push.data.subscribed ? tCommon("on") : tCommon("off"),
        }
      : undefined,
    appearance: theme in themes ? { meta: themes[theme as keyof typeof themes] } : undefined,
    fiestabot: provider ? { meta: provider.name } : undefined,
    network:
      wifi.data?.connected && wifi.data.ssid ? { meta: tHub("networkMeta", { ssid: wifi.data.ssid }) } : undefined,
  };
}

interface SettingsGroupListProps {
  label: string;
  sections: readonly (typeof SETTINGS_SECTIONS)[number][];
  active: SettingsSectionId | null;
  title: (id: SettingsSectionId) => string;
  meta: RowMeta;
}

/** One group of the index: its label, then a row per section. */
function SettingsGroupList({ label, sections, active, title, meta }: SettingsGroupListProps) {
  const labelId = useId();
  if (sections.length === 0) return null;
  return (
    <Stack gap="2">
      {/* Flush with the card edge (07e `320:7936`: "YOU" at x 16). */}
      <Text id={labelId} size="xs" tone="muted" weight="medium" className="uppercase">
        {label}
      </Text>
      {/* 07e "Settings row": rows sit inset in the card (its border plus 4px),
          2px apart, each its own rounded hover/selected fill, with no
          dividers — BB-FC-2. */}
      <ListRowGroup aria-labelledby={labelId} className={INSET_ROW_GROUP}>
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
                className={INSET_ROW}
                title={title(id)}
                description={meta[id]?.description}
                // Trailing values are Text/xs ("System", "Off").
                meta={
                  meta[id]?.meta == null ? undefined : (
                    <Text as="span" size="xs" tone="muted">
                      {meta[id]?.meta}
                    </Text>
                  )
                }
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
  const { boards, isLoading: boardsLoading } = useCurrentBoard();
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
    case "fiestabot":
      return <FiestaBotSettings />;
    case "accessibility":
      return <AccessibilitySettings />;
    case "network":
      return (
        <>
          <NetworkAddresses />
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
          {/* 07e 320:8881: Version, then Backups, first. */}
          <ReleaseChannelCard />
          <BackupSettings />
          <InstanceNameCard />
          <SystemControls />
          <AutoUpdateIntervalCard />
          {!boardsLoading && boards.every(isUntouchedPlaceholder) && (
            <Card>
              <CardHeader>
                {/* 07e card scale, as SettingsPanel draws it (BB-FC-1). */}
                <CardTitle size="base" className="text-sm leading-5">
                  {t("setupWizardTitle")}
                </CardTitle>
                <CardDescription className="text-xs">{t("setupWizardDescription")}</CardDescription>
              </CardHeader>
              <CardContent>
                <Button variant="brand" onClick={triggerWizard} className="gap-2 btn-lift">
                  <Wand2 className="h-4 w-4" />
                  {t("runSetupWizard")}
                </Button>
              </CardContent>
            </Card>
          )}
          <DebugSettings />
          {/* The About box's only home on a phone (the rail keeps it in the
              account menu too). Same dialog, not a second About card. */}
          <SettingsPanel>
            <Button variant="outline" onClick={() => setAboutOpen(true)} className="gap-2">
              <Info className="h-4 w-4" aria-hidden="true" />
              {tMenu("about")}
            </Button>
            <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
          </SettingsPanel>
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
