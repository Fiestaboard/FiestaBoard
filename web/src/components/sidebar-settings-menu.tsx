"use client";

/** App-owned identity, appearance and navigation in the sidebar footer. */

import {
  Avatar,
  Box,
  Button,
  Flex,
  Popover,
  PopoverContent,
  PopoverTrigger,
  SegmentedControl,
  SegmentedControlItem,
  SidebarAccountTrigger,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpCircle, ChevronRight, Info, LogOut, Monitor, Moon, Settings, Sun } from "lucide-react";
import { useState } from "react";

import { AboutDialog } from "@/components/about-dialog";
import { useAvailableUpdate } from "@/hooks/use-available-update";
import { useRouter } from "@/hooks/use-router";
import { useTheme } from "@/hooks/use-theme";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

interface SidebarSettingsMenuProps {
  /** Avatar-only trigger, matching the 64px rail. Desktop only. */
  collapsed?: boolean;
  /**
   * Which chrome is hosting the slot. `"mobile"` is the drawer, where the
   * rows render inline; `"desktop"` is the rail, where they live in a
   * dropdown. Comes straight from FiestaUI's `renderSettingsMenu` context.
   */
  variant?: "mobile" | "desktop";
  /**
   * The words for the trigger's dot ("Update available"), straight from the
   * slot context's `notice`. NavigationSidebar decides it once and hands it to
   * the Sidebar as `menuNotice`; this only forwards it, so the rail's dot and
   * the mobile hamburger's cannot disagree. Unused on mobile, where there is
   * no trigger and the Sidebar dots the hamburger itself.
   */
  notice?: string;
  /**
   * Called when a mobile row navigates away — the Sidebar's `closeMenu`. The
   * drawer is an overlay with no idea these rows navigate: left open, it
   * covers the page Settings just routed to, and the tap reads as a no-op.
   * The desktop dropdown closes itself and never calls this.
   */
  onSelect?: () => void;
}

export function SidebarSettingsMenu({
  collapsed = false,
  variant = "desktop",
  notice,
  onSelect,
}: SidebarSettingsMenuProps) {
  const t = useTranslations("settingsMenu");
  const { theme, setTheme } = useTheme();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [aboutOpen, setAboutOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const { data: authStatus } = useQuery({
    queryKey: ["auth-status"],
    queryFn: api.getAuthStatus,
    staleTime: 30_000,
    retry: false,
  });

  const signedIn = Boolean(authStatus?.enabled && authStatus.authenticated);
  const username = signedIn ? (authStatus?.username ?? null) : null;

  // Shared cache key with AboutDialog, so opening either usually costs no
  // request.
  const { data: version } = useQuery({
    queryKey: ["version"],
    queryFn: () => api.getVersion(),
    staleTime: Infinity,
    retry: false,
  });
  // The hook NavigationSidebar decides the dot with, so this item and the dot
  // cannot disagree. Same cache keys, so it costs no second request.
  const updateAvailable = useAvailableUpdate();

  // The trigger says who you are when the install knows, and what the menu
  // is when it doesn't. An install with auth off has no name to show, so the
  // fallback is "More" with an ellipsis in the avatar's place. Not
  // "Settings": the gear beside the trigger is already that, and two
  // adjacent controls with one name and different behaviour is a trap.
  const label = username ?? t("trigger");

  const handleSignOut = async () => {
    try {
      await api.logout();
    } catch {
      // Best-effort — the server cookie clear may fail but we still want to
      // drop the client cache and bounce to /login.
    }
    queryClient.removeQueries({ queryKey: ["auth-status"] });
    router.replace("/login");
  };

  const openSettings = () => router.push("/settings");
  const openAccount = () => router.push("/settings?section=account");
  const selectDesktop = (action: () => void) => () => {
    setMenuOpen(false);
    action();
  };

  // Mobile rows that leave for another route close the drawer first. About
  // does not: its dialog opens over the drawer and closes back onto it.
  const selectThen = (action: () => void) => () => {
    onSelect?.();
    action();
  };

  // An update is something you act on, not a fact you read. `SystemUpdate`
  // renders at the top of /settings — above the tab strip, and nothing at all
  // when the install is current — so /settings with no anchor lands the reader
  // on the button that applies it. This replaces the passive badge that named
  // the waiting version and then left you to go find the updater.
  const updateLabel = updateAvailable ? t("updateTo", { version: updateAvailable }) : null;

  const versionLine = version ? `${version.running_version}${version.is_dev ? ` · ${t("devSuffix")}` : ""}` : null;

  if (variant === "mobile") {
    return (
      <>
        {/* The drawer's footer is `shrink-0` inside an `overflow-hidden`
            panel, so this block cannot rely on the panel to scroll it — too
            tall and it is clipped, not scrolled. Hence the compact shape
            (label beside control, About and Sign out sharing a row) and its
            own scroll ceiling as a backstop on very short viewports. */}
        <Stack gap="0.5" className="max-h-[60dvh] overflow-y-auto">
          {/* The drawer has no trigger, so this row is where the avatar and
              name go. px-2 + gap-1 are measured, not chosen: they put the
              24px avatar's centre on the icons' column below it and the name
              on their labels' edge. */}
          {username && (
            <Flex align="center" gap="1" className="px-2 py-1">
              <Avatar size="sm" name={username} />
              <Text size="sm" className="min-w-0 truncate font-medium">
                {username}
              </Text>
            </Flex>
          )}

          {signedIn && (
            <Button variant="ghost" className="h-11 w-full justify-start gap-2 px-2" onClick={selectThen(openAccount)}>
              <Avatar size="sm" name={username ?? undefined} />
              {t("account")}
            </Button>
          )}

          <Button variant="ghost" className="h-11 w-full justify-start gap-2 px-2" onClick={selectThen(openSettings)}>
            <Settings className="h-4 w-4 shrink-0" aria-hidden="true" />
            {t("settings")}
          </Button>

          <Flex align="center" justify="between" gap="2" className="px-2 py-1">
            <Text size="xs" tone="muted" className="shrink-0">
              {t("appearance")}
            </Text>
            {/* Icon-only with real labels: three words plus a heading do not
                fit a 366px row, and sun/moon/monitor is the one icon set
                every reader already knows. `size="md"` is a 32px target
                rather than the 28px `sm` the desktop rail can afford. */}
            <SegmentedControl
              aria-label={t("appearance")}
              size="md"
              value={theme}
              onValueChange={(value) => setTheme(value as "light" | "dark" | "system")}
            >
              <SegmentedControlItem value="light" aria-label={t("light")} title={t("light")}>
                <Sun aria-hidden="true" />
              </SegmentedControlItem>
              <SegmentedControlItem value="dark" aria-label={t("dark")} title={t("dark")}>
                <Moon aria-hidden="true" />
              </SegmentedControlItem>
              <SegmentedControlItem value="system" aria-label={t("system")} title={t("system")}>
                <Monitor aria-hidden="true" />
              </SegmentedControlItem>
            </SegmentedControl>
          </Flex>

          {versionLine && (
            <Text size="xs" tone="muted" className="truncate px-2 py-1">
              {versionLine}
            </Text>
          )}

          {updateLabel && (
            <Button
              variant="ghost"
              className="h-11 w-full justify-start gap-2 px-2 text-brand-emphasis"
              onClick={selectThen(openSettings)}
            >
              <ArrowUpCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
              <Text as="span" className="truncate">
                {updateLabel}
              </Text>
              <ChevronRight className="ml-auto h-4 w-4 shrink-0" aria-hidden="true" />
            </Button>
          )}

          {/* Secondary, so they share a row rather than each taking 44px of a
              drawer that still has to show the nav above it. */}
          <Flex align="center" gap="1">
            <Button
              variant="ghost"
              className="h-11 min-w-0 flex-1 justify-start gap-2 px-2"
              onClick={() => setAboutOpen(true)}
            >
              <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
              <Text as="span" className="truncate">
                {t("about")}
              </Text>
            </Button>
            {signedIn && (
              <Button
                variant="ghost"
                className="h-11 min-w-0 flex-1 justify-start gap-2 px-2"
                onClick={selectThen(handleSignOut)}
              >
                <LogOut className="h-4 w-4 shrink-0" aria-hidden="true" />
                <Text as="span" className="truncate">
                  {t("signOut")}
                </Text>
              </Button>
            )}
          </Flex>
        </Stack>

        <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
      </>
    );
  }

  return (
    <>
      <Popover open={menuOpen} onOpenChange={setMenuOpen}>
        <PopoverTrigger asChild>
          <SidebarAccountTrigger label={label} anonymous={!username} collapsed={collapsed} notice={notice} />
        </PopoverTrigger>
        <PopoverContent
          side="top"
          align="start"
          sideOffset={8}
          label={t("popoverLabel")}
          className="w-[304px] max-w-[calc(100vw-24px)] max-h-[var(--available-height)] overflow-y-auto p-0"
        >
          {username && (
            <Flex align="center" gap="3" className="border-b p-3">
              <Avatar size="md" name={username} />
              <Box className="min-w-0 flex-1">
                <Text size="sm" weight="medium" className="break-words">
                  {username}
                </Text>
                <Button variant="link" className="h-auto p-0 text-xs" onClick={selectDesktop(openAccount)}>
                  {t("account")}
                  <ChevronRight className="size-3" aria-hidden="true" />
                </Button>
              </Box>
            </Flex>
          )}
          <Stack gap="2" className="border-b p-3">
            <Text size="xs" tone="muted">
              {t("appearance")}
            </Text>
            <SegmentedControl
              aria-label={t("appearance")}
              size="md"
              className="w-full"
              value={theme}
              onValueChange={(value) => setTheme(value as "light" | "dark" | "system")}
            >
              <SegmentedControlItem value="light">
                <Sun aria-hidden="true" />
                {t("light")}
              </SegmentedControlItem>
              <SegmentedControlItem value="dark">
                <Moon aria-hidden="true" />
                {t("dark")}
              </SegmentedControlItem>
              <SegmentedControlItem value="system">
                <Monitor aria-hidden="true" />
                {t("system")}
              </SegmentedControlItem>
            </SegmentedControl>
          </Stack>
          <Stack gap="0.5" className="p-1.5">
            <Button variant="ghost" className="w-full justify-start gap-2" onClick={selectDesktop(openSettings)}>
              <Settings className="size-4" aria-hidden="true" />
              {t("settings")}
            </Button>
            <Button
              variant="ghost"
              className="w-full justify-start gap-2"
              onClick={selectDesktop(() => setAboutOpen(true))}
            >
              <Info className="size-4" aria-hidden="true" />
              {t("about")}
            </Button>
            {versionLine && (
              <Text size="xs" tone="muted" className="px-3 py-1">
                {versionLine}
              </Text>
            )}
            {updateLabel && (
              <Button
                variant="ghost"
                className="w-full justify-start gap-2 text-brand-emphasis"
                onClick={selectDesktop(openSettings)}
              >
                <ArrowUpCircle className="size-4 shrink-0" aria-hidden="true" />
                <Text as="span" className="truncate">
                  {updateLabel}
                </Text>
              </Button>
            )}
          </Stack>
          {signedIn && (
            <Box className="border-t p-1.5">
              <Button variant="ghost" className="w-full justify-start gap-2" onClick={selectDesktop(handleSignOut)}>
                <LogOut className="size-4" aria-hidden="true" />
                {t("signOut")}
              </Button>
            </Box>
          )}
        </PopoverContent>
      </Popover>
      <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
    </>
  );
}
