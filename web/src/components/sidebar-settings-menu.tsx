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
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  SidebarSettingsTrigger,
  Text,
} from "@fiestaboard/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpCircle, Info, LogOut, Monitor, Moon, Settings, Sun } from "lucide-react";
import { useState } from "react";

import { AboutDialog } from "@/components/about-dialog";
import { useRouter } from "@/hooks/use-router";
import { useTheme } from "@/hooks/use-theme";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

interface SidebarSettingsMenuProps {
  /** Icon-only trigger, matching the 64px rail. */
  collapsed?: boolean;
}

export function SidebarSettingsMenu({ collapsed = false }: SidebarSettingsMenuProps) {
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
          {version && (
            <DropdownMenuLabel className="flex items-center justify-between gap-2 font-normal text-muted-foreground">
              <Text as="span" className="truncate">
                {version.running_version}
                {version.is_dev && ` · ${t("devSuffix")}`}
              </Text>
              {updateAvailable && (
                <Text
                  as="span"
                  className="inline-flex shrink-0 items-center gap-1 text-brand-emphasis"
                  data-testid="settings-menu-update-badge"
                >
                  <ArrowUpCircle className="h-3.5 w-3.5" aria-hidden="true" />
                  {/* The icon carries the meaning for sighted readers and
                      the version number sits beside it; assistive tech gets
                      the whole sentence instead of "arrow, 8.39.0". */}
                  <Text as="span" className="sr-only">
                    {t("updateAvailable", { version: updateAvailable })}
                  </Text>
                  <Text as="span" aria-hidden="true">
                    {updateAvailable}
                  </Text>
                </Text>
              )}
            </DropdownMenuLabel>
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
