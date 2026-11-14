"use client";

import { BoardSelector, Sidebar, type SidebarLinkProps, type SidebarNavItem } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";

import { useCurrentBoard } from "@/components/current-board-context";
import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { MoreSheetExtras } from "@/components/more-sheet";
import { readStoredCollapsed, useSidebar } from "@/components/sidebar-context";
import { SidebarSettingsMenu } from "@/components/sidebar-settings-menu";
import { ViewTransitionLink } from "@/components/view-transition-link";
import { useAvailableUpdate } from "@/hooks/use-available-update";
import { RAIL_BREAKPOINT, useBelowRail, useTabletRailCollapse } from "@/hooks/use-below-rail";
import { usePrefetchPagesData } from "@/hooks/use-board";
import { useHubLine } from "@/hooks/use-hub-connection";
import { usePathname } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { type AISettings, api } from "@/lib/api";
import { isChromelessPath } from "@/lib/chromeless";
import { MAX_APP_WIDTH, SIDEBAR_INSET } from "@/lib/layout-constants";
import { integrationsNeedingAttention, isNavItemActive, type NavItemDef, navItemsFor } from "@/lib/nav-items";

/**
 * App wiring around the design system's presentational <Sidebar> — routes,
 * i18n labels, board context, collapse persistence and the AI feature flag
 * all live here; every pixel lives in @fiestaboard/ui.
 */
export function NavigationSidebar() {
  const pathname = usePathname();
  const prefetchPages = usePrefetchPagesData();
  const { collapsed, transitioning, toggle, setCollapsed, onTransitionEnd } = useSidebar();
  useTabletRailCollapse(setCollapsed, readStoredCollapsed);
  const t = useTranslations("navigation");
  const tMenu = useTranslations("settingsMenu");
  const { isOpen: aiPanelOpen, open: openAiPanel } = useGlobalAiPanel();
  const { boards, currentBoardId, setCurrentBoardId } = useCurrentBoard();

  // The chromeless early-return below runs AFTER hooks, so these queries
  // must be gated too or the TV viewer fires them (authenticated, 401 +
  // retries on every wall-display load).
  const chromeless = isChromelessPath(pathname);

  const { data: aiSettings } = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: () => api.getAiSettings(),
    enabled: !chromeless,
  });
  const hasAiProviders = (aiSettings?.enabled ?? false) && (aiSettings?.providers?.length ?? 0) > 0;

  // Decided here, once, because `menuNotice` is one prop for both
  // breakpoints: the Sidebar hands it back to the rail's account trigger and
  // puts it on the mobile hamburger itself. The "Update to X.Y.Z" item was
  // always in the menu; nothing on the closed button said to open it.
  const updateAvailable = useAvailableUpdate({ enabled: !chromeless });

  // The Integrations badge (07a "ONE BADGE, ONE STORY"). Same cache key as
  // the Integrations page, so visiting it refreshes the badge for free.
  const { data: pluginList } = useQuery({
    queryKey: ["plugins"],
    queryFn: api.listPlugins,
    staleTime: 60_000,
    enabled: !chromeless,
  });
  const needsAttention = integrationsNeedingAttention(pluginList?.plugins);

  // Below 768px the tab bar is the nav (WEB-01/02). It and the rail are one
  // Sidebar, but they list different things: the bar has no row for nested
  // Collections, and its More drawer holds the Hub group instead of the
  // account menu (07a `308:36070`).
  const belowRail = useBelowRail();
  const chrome = belowRail ? "bottom-nav" : "rail";

  // The hub line under the switcher (WEB-09, slice 2.3): "host · Online /
  // Remote / Can't reach". The same source as the More drawer's foot line
  // (useHubLine). The switcher only renders with two or more boards, so a
  // single-board install adds no status poll for it.
  const tHub = useTranslations("statusBanners");
  const { host: hubHost, status: hubStatus } = useHubLine({ enabled: !chromeless && boards.length > 1 });

  // Hide the sidebar on chrome-less screens: auth screens (the user isn't
  // navigating anywhere until they sign in) and the FiestaPanel TV viewer
  // (a wall display must never grow app chrome).
  if (chromeless) return null;

  const toNavItem = (item: NavItemDef): SidebarNavItem => ({
    key: item.key,
    href: item.href,
    icon: item.icon,
    label: t(item.key),
    external: item.external,
    active: isNavItemActive(item, pathname, chrome),
    onPrefetch: !item.external && item.href === "/pages" ? prefetchPages : undefined,
    badge:
      item.key === "integrations" && needsAttention > 0
        ? { count: needsAttention, label: t("needsAttention", { count: needsAttention }) }
        : undefined,
  });

  const renderLink = ({ children, ...props }: SidebarLinkProps) => (
    <ViewTransitionLink {...props}>{children}</ViewTransitionLink>
  );

  const boardSelectorLabels = {
    boardSelector: t("boardSelector"),
    selectBoard: t("selectBoard"),
    unnamedBoard: t("unnamedBoard"),
    hubStatus: { online: tHub("hubOnline"), remote: tHub("hubRemote"), unreachable: tHub("hubUnreachable") },
  };

  return (
    <Sidebar
      labels={{
        mainNavigation: t("mainNavigation"),
        primaryNavigation: t("primaryNavigation"),
        navigationMenu: t("navigationMenu"),
        openMenu: t("openMenu"),
        closeMenu: t("closeMenu"),
        expandSidebar: t("expandSidebar"),
        collapseSidebar: t("collapseSidebar"),
        aiAssistant: t("aiAssistant"),
        more: t("more"),
      }}
      // Below 768px a tab bar (Home · Pages · Schedule · Displays · More);
      // from 768px the rail. MainContent takes the same breakpoint.
      variant="bottom-nav"
      railBreakpoint={RAIL_BREAKPOINT}
      items={navItemsFor(chrome).map(toNavItem)}
      renderLink={renderLink}
      collapsed={collapsed}
      transitioning={transitioning}
      onToggleCollapsed={toggle}
      onTransitionEnd={onTransitionEnd}
      ai={hasAiProviders ? { active: aiPanelOpen, onOpen: openAiPanel } : undefined}
      // The gear left of the assistant: a one-click shortcut. Settings has a
      // row in the list now (WEB-01), and the row is what says "you are
      // here" (07e `318:46000` draws the gear unlit on /settings), so the
      // gear never lights.
      settings={{ href: "/settings", label: t("settings") }}
      boardSelector={
        boards.length > 1 ? (
          <BoardSelector
            boards={boards}
            value={currentBoardId}
            onChange={setCurrentBoardId}
            labels={boardSelectorLabels}
            collapsed={collapsed}
            host={hubHost}
            status={hubStatus}
          />
        ) : undefined
      }
      mobileBoardSelector={
        boards.length > 1 ? (
          <BoardSelector
            boards={boards}
            value={currentBoardId}
            onChange={setCurrentBoardId}
            labels={boardSelectorLabels}
            variant="mobileHeader"
            host={hubHost}
            status={hubStatus}
          />
        ) : undefined
      }
      // The rail's footer is the account menu. On a phone the same slot is
      // the foot of the More drawer, which 07a fills with FiestaBot and the
      // Hub group; the account rows (sign out, theme, About) live in
      // Settings › Account and Appearance there.
      // `notice` is `menuNotice` coming back; forwarded, not recomputed.
      renderSettingsMenu={({ variant, collapsed: isCollapsed, notice, closeMenu }) =>
        variant === "mobile" ? (
          <MoreSheetExtras ai={hasAiProviders ? { onOpen: openAiPanel } : undefined} closeMenu={closeMenu} />
        ) : (
          <SidebarSettingsMenu variant={variant} collapsed={isCollapsed} notice={notice} onSelect={closeMenu} />
        )
      }
      menuNotice={updateAvailable ? tMenu("updateAvailable") : undefined}
      maxWidth={MAX_APP_WIDTH}
      sidebarInset={SIDEBAR_INSET}
    />
  );
}
