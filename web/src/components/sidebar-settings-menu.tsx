"use client";

/**
 * The rail footer's settings menu — the app half of FiestaUI's
 * `renderSettingsMenu` slot.
 *
 * Everything in here is app knowledge the design system has no business
 * holding: who is signed in, where `/settings` is, which theme is active,
 * and what the build number is. FiestaUI owns the trigger's paint
 * (`SidebarSettingsTrigger`) and the footer's layout; this owns the
 * contents.
 *
 * It replaces three separate rail affordances — the version string, the
 * theme toggle, and the sign-out row — none of which was worth the width it
 * took, and one of which (the version) could only render wrongly on the
 * collapsed rail.
 *
 * **Two shapes, one set of facts.** On the desktop rail the footer slot is a
 * narrow column, so the contents belong in a dropdown. In the mobile drawer
 * they do not: the drawer is already an overlay, its footer trigger is
 * full-width, and a 224px popup hanging off it — a second thing to dismiss,
 * over a panel the user just opened — was the whole of what "doesn't look
 * great on mobile" meant. So `variant="mobile"` renders the same facts as
 * inline rows instead. FiestaUI has always passed the variant into this slot;
 * the app simply threw it away.
 *
 * Inline rows are not a menu, which is why the mobile theme control can be a
 * real `SegmentedControl` while the desktop one stays three
 * `DropdownMenuRadioItem`s: inside a menu, arrow keys move between items, and
 * a radiogroup embedded there would break that contract.
 */

import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Flex,
  SegmentedControl,
  SegmentedControlItem,
  SidebarSettingsTrigger,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpCircle, ChevronRight, Info, LogOut, Monitor, Moon, Settings, Sun } from "lucide-react";
import { useState } from "react";

import { AboutDialog } from "@/components/about-dialog";
import { useRouter } from "@/hooks/use-router";
import { useTheme } from "@/hooks/use-theme";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

interface SidebarSettingsMenuProps {
  /** Icon-only trigger, matching the 64px rail. Desktop only. */
  collapsed?: boolean;
  /**
   * Which chrome is hosting the slot. `"mobile"` is the drawer, where the
   * rows render inline; `"desktop"` is the rail, where they live in a
   * dropdown. Comes straight from FiestaUI's `renderSettingsMenu` context.
   */
  variant?: "mobile" | "desktop";
}

export function SidebarSettingsMenu({ collapsed = false, variant = "desktop" }: SidebarSettingsMenuProps) {
  const t = useTranslations("settingsMenu");
  const { theme, setTheme } = useTheme();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [aboutOpen, setAboutOpen] = useState(false);

  const { data: authStatus } = useQuery({
    queryKey: ["auth-status"],
    queryFn: api.getAuthStatus,
    staleTime: 30_000,
    retry: false,
  });

  const signedIn = Boolean(authStatus?.enabled && authStatus.authenticated);
  const username = signedIn ? (authStatus?.username ?? null) : null;

  // Shared cache keys with AboutDialog, so opening either usually costs no
  // request. Not gated on the menu being open, unlike About's copies: the
  // whole point of an update indicator is that it is there before you go
  // looking for it.
  const { data: version } = useQuery({
    queryKey: ["version"],
    queryFn: () => api.getVersion(),
    staleTime: Infinity,
    retry: false,
  });
  const { data: updateStatus } = useQuery({
    queryKey: ["update-status"],
    queryFn: () => api.getUpdateStatus(),
    staleTime: 1000 * 30,
    retry: false,
  });
  const { data: updateCheck } = useQuery({
    queryKey: ["update-check"],
    queryFn: () => api.checkForUpdate(),
    staleTime: 1000 * 60 * 60,
    retry: false,
  });

  // Same rule as AboutDialog, and it is not cosmetic: when an external
  // supervisor owns updates (the Home Assistant add-on) FiestaBoard cannot
  // apply one, so pointing at it would be an offer it cannot honour.
  const updateAvailable =
    !updateStatus?.managed_externally && updateCheck?.update_available ? updateCheck.latest_version : null;

  // The trigger says who you are when the install knows, and what the menu
  // is when it doesn't. An install with auth off has no name to show and
  // "Settings" is what is actually behind the gear, so the fallback is a
  // description rather than a placeholder.
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
          {username && (
            <Text size="xs" tone="muted" className="truncate px-2 py-1">
              {username}
            </Text>
          )}

          <Button variant="ghost" className="h-11 w-full justify-start gap-2 px-2" onClick={openSettings}>
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
              onClick={openSettings}
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
              <Button variant="ghost" className="h-11 min-w-0 flex-1 justify-start gap-2 px-2" onClick={handleSignOut}>
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
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <SidebarSettingsTrigger label={label} collapsed={collapsed} />
        </DropdownMenuTrigger>
        {/* side="top": the trigger is the bottom-most thing on the rail, so
            the menu has nowhere to go but up. align="start" keeps its left
            edge on the trigger's, which on the collapsed rail is what stops
            it opening off the left of the screen. */}
        <DropdownMenuContent side="top" align="start" sideOffset={8} className="w-56">
          {username && (
            <>
              <DropdownMenuLabel>{username}</DropdownMenuLabel>
              <DropdownMenuSeparator />
            </>
          )}

          <DropdownMenuItem onClick={() => router.push("/settings")}>
            <Settings aria-hidden="true" />
            {t("settings")}
          </DropdownMenuItem>

          <DropdownMenuSeparator />

          <DropdownMenuGroup>
            <DropdownMenuLabel>{t("appearance")}</DropdownMenuLabel>
            {/* Three choices with the current one checked, not a two-state
                toggle. The toggle this replaces could not express "follow
                the system", which is the default the app actually ships —
                so a fresh install showed a sun-or-moon button that disagreed
                with the theme on screen. */}
            <DropdownMenuRadioGroup
              value={theme}
              onValueChange={(value) => setTheme(value as "light" | "dark" | "system")}
            >
              <DropdownMenuRadioItem value="light">
                <Sun aria-hidden="true" />
                {t("light")}
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="dark">
                <Moon aria-hidden="true" />
                {t("dark")}
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="system">
                <Monitor aria-hidden="true" />
                {t("system")}
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuGroup>

          <DropdownMenuSeparator />

          {/* The version, stated here rather than only inside About. About
              is one click further away, and the build number is the thing
              people come to this menu to read — so it earns its line even
              though About repeats it. #2038 moved the version off the rail
              (where the collapsed state could only render it wrongly); this
              puts it back where there is room for it. */}
          {versionLine && (
            <DropdownMenuLabel className="font-normal text-muted-foreground">
              <Text as="span" className="truncate">
                {versionLine}
              </Text>
            </DropdownMenuLabel>
          )}

          {/* The version line above states what is running; this states what
              to do about it. It replaced a badge on that line which named the
              waiting version and went nowhere — two mentions of 8.39.0 in a
              224px menu, neither of them clickable. */}
          {updateLabel && (
            <DropdownMenuItem onClick={openSettings} className="text-brand-emphasis">
              <ArrowUpCircle aria-hidden="true" />
              {updateLabel}
            </DropdownMenuItem>
          )}

          <DropdownMenuItem onClick={() => setAboutOpen(true)}>
            <Info aria-hidden="true" />
            {t("about")}
          </DropdownMenuItem>

          {signedIn && (
            <DropdownMenuItem onClick={handleSignOut}>
              <LogOut aria-hidden="true" />
              {t("signOut")}
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Outside the menu, deliberately: the menu unmounts as it closes, and
          a dialog mounted inside it would go with it. */}
      <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
    </>
  );
}
