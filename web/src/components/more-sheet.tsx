"use client";

import { Box, NavList, NavListItem, NavListLink, Text } from "@fiestaboard/ui";
import { Sparkles } from "lucide-react";
import { useId } from "react";

import { HubLine } from "@/components/hub-line";
import { ViewTransitionLink } from "@/components/view-transition-link";
import { useHubIdentity } from "@/hooks/use-hub-identity";
import { usePathname } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { HUB_SETTINGS_LINKS } from "@/lib/nav-items";
import { settingsSectionHref } from "@/lib/settings-sections";

/**
 * The 48px rows of the More drawer, in NavList's own words: its documented
 * escape hatch for the mobile menu's taller row ("the same row with more
 * padding"), matched to the drawer's built-in rows above it (px-4, gap-3,
 * 16px label in the foreground ink, 20px glyph) so the two halves read as
 * one list.
 */
const MORE_ROW = "min-h-12 gap-3 px-4 text-base text-foreground [&>svg]:size-5";

interface MoreSheetExtrasProps {
  /** FiestaBot, when a provider is set up: opens the global drawer. */
  ai?: { onOpen: () => void };
  /** The Sidebar's `closeMenu`, so a row that navigates closes the drawer behind it. */
  closeMenu: () => void;
}

/**
 * The lower half of the phone's More surface (07a `308:36070`), rendered into
 * the Sidebar's More drawer through `renderSettingsMenu({ variant: "mobile" })`:
 *
 *   FiestaBot · Opens the drawer
 *   ─────────
 *   HUB · MAYA'S FIESTAPI
 *   Network · AI provider · System & backups · Language & time
 *   ● fiestapi.local · Online · FiestaBoard 11.1.0
 *
 * The upper half (Integrations · Staff Picks · Settings · Help & Docs) is the
 * Sidebar's own drawer list, fed from the same IA as the rail.
 *
 * TODO(FiestaUI 1.4g): the 07a More sheet is a floating bottom sheet with a
 * grabber, a "More" title and chevron rows. Sidebar `variant="bottom-nav"`
 * opens its built-in drawer and has no hook to open an app sheet instead, and
 * the 1.3 Sheet has no floating variant; until both land, the drawer is the
 * interim surface (status/web-2.1.md, Jev p=0.82).
 */
export function MoreSheetExtras({ ai, closeMenu }: MoreSheetExtrasProps) {
  const t = useTranslations("navigation");
  const tSettings = useTranslations("settings.hub");
  const pathname = usePathname();
  const hub = useHubIdentity();
  const hubHeadingId = useId();

  return (
    // The drawer's footer does not scroll with its list (FiestaUI pins it),
    // so this block carries its own ceiling for short viewports.
    <Box className="-mx-3 -my-3 max-h-[55dvh] overflow-y-auto py-2" data-slot="more-extras">
      {ai && (
        <>
          <NavList className="px-3">
            <NavListItem>
              <NavListLink asChild className={MORE_ROW}>
                <button
                  type="button"
                  onClick={() => {
                    closeMenu();
                    ai.onOpen();
                  }}
                >
                  <Sparkles aria-hidden="true" />
                  <Text as="span" size="base" className="flex-1">
                    {t("fiestaBot")}
                  </Text>
                  <Text as="span" size="xs" tone="muted">
                    {t("opensDrawer")}
                  </Text>
                </button>
              </NavListLink>
            </NavListItem>
          </NavList>
          <Box className="mx-3 my-2 border-t border-sidebar-border" role="presentation" />
        </>
      )}

      <Text id={hubHeadingId} size="xs" tone="muted" weight="medium" className="px-7 pt-1 pb-1 font-mono uppercase">
        {tSettings("hubGroup", { name: hub.name ?? tSettings("hubFallbackName") })}
      </Text>
      <NavList className="px-3" aria-labelledby={hubHeadingId}>
        {HUB_SETTINGS_LINKS.map(({ section, icon: Icon }) => {
          const href = settingsSectionHref(section);
          return (
            <NavListItem key={section}>
              <NavListLink asChild active={pathname === href} className={MORE_ROW}>
                <ViewTransitionLink href={href} onClick={closeMenu}>
                  <Icon aria-hidden="true" />
                  {tSettings(`sections.${section}.title`)}
                </ViewTransitionLink>
              </NavListLink>
            </NavListItem>
          );
        })}
      </NavList>
      <HubLine hub={hub} className="px-7 pt-2 pb-1" />
    </Box>
  );
}
