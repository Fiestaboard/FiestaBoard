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
} from "@fiestaboard/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, LogOut, Monitor, Moon, Settings, Sun } from "lucide-react";
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
