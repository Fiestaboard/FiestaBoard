"use client";

import { BoardSelector, fireSeasonBurst, Sidebar, type SidebarLinkProps, type SidebarNavItem } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import {
  Award,
  Calendar,
  FileText,
  FlaskConical,
  GalleryHorizontalEnd,
  HelpCircle,
  Home,
  Puzzle,
  Settings,
} from "lucide-react";
import { useCallback } from "react";
import { toast } from "sonner";

import { useCurrentBoard } from "@/components/current-board-context";
import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { SidebarAccount } from "@/components/sidebar-account";
import { useSidebar } from "@/components/sidebar-context";
import { ThemeToggle } from "@/components/theme-toggle";
import { VersionDisplay } from "@/components/version-display";
import { ViewTransitionLink } from "@/components/view-transition-link";
import { usePrefetchPagesData } from "@/hooks/use-board";
import { useActiveSeason } from "@/hooks/use-pride-active";
import { usePathname } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { type AISettings, api } from "@/lib/api";
import { appUrl } from "@/lib/base-path";
import { MAX_APP_WIDTH, SIDEBAR_INSET } from "@/lib/layout-constants";

interface NavItemDef {
  key: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  external?: boolean;
}

const primaryItems: NavItemDef[] = [
  { key: "home", href: "/", icon: Home },
  { key: "pages", href: "/pages", icon: FileText },
  { key: "collections", href: "/collections", icon: GalleryHorizontalEnd },
  { key: "schedule", href: "/schedule", icon: Calendar },
  { key: "integrations", href: "/integrations", icon: Puzzle },
];

// Shown only while the transition-plugins beta flag is on (see
// `showTransitionsLab` below) — the whole feature is invisible otherwise.
const transitionsLabItem: NavItemDef = { key: "transitions", href: "/transitions", icon: FlaskConical };

const secondaryItems: NavItemDef[] = [
  { key: "picks", href: "/picks", icon: Award },
  { key: "helpDocs", href: "https://fiestaboard.app/docs/intro", icon: HelpCircle, external: true },
  { key: "settings", href: "/settings", icon: Settings },
];

/**
 * App wiring around the design system's presentational <Sidebar> — routes,
 * i18n labels, board context, collapse persistence, AI/beta feature flags,
 * and the seasonal celebration all live here; every pixel lives in
 * @fiestaboard/ui.
 */
export function NavigationSidebar() {
  const pathname = usePathname();
  const prefetchPages = usePrefetchPagesData();
  const { collapsed, transitioning, toggle, onTransitionEnd } = useSidebar();
  const t = useTranslations("navigation");
  const { isOpen: aiPanelOpen, open: openAiPanel } = useGlobalAiPanel();
  const { boards, currentBoardId, setCurrentBoardId } = useCurrentBoard();

  const season = useActiveSeason();

  const fireCelebration = useCallback(
    (e: React.MouseEvent) => {
      if (!season) return;
      fireSeasonBurst(e, season.colors);
      toast.custom(() => (
        <div className="flex items-center gap-2 rounded-full border border-white/10 bg-[#111] px-5 py-2.5 text-[15px] font-bold shadow-xl">
          <span
            style={{
              background: "linear-gradient(90deg, #e40303, #ff8c00, #ffed00, #008026, #004dff, #750787)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            Happy Pride!
          </span>{" "}
          🏳️‍🌈
        </div>
      ));
    },
    [season],
  );

  const { data: aiSettings } = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: () => api.getAiSettings(),
  });
  const hasAiProviders = (aiSettings?.enabled ?? false) && (aiSettings?.providers?.length ?? 0) > 0;

  const { data: betaData } = useQuery({
    queryKey: ["settings", "beta"],
    queryFn: () => api.getBetaSettings(),
  });
  const showTransitionsLab = betaData?.settings.transition_plugins_enabled ?? false;
  const navPrimaryItems = showTransitionsLab ? [...primaryItems, transitionsLabItem] : primaryItems;

  // Hide the sidebar on auth screens — the user isn't navigating
  // anywhere until they sign in / finish setup, and chrome around
  // the login form makes a fresh install look broken.
  if (pathname.startsWith("/login")) return null;

  const isActive = (item: NavItemDef) => {
    if (item.external) return false;
    return item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/");
  };

  const toNavItem = (item: NavItemDef): SidebarNavItem => ({
    key: item.key,
    href: item.href,
    icon: item.icon,
    label: t(item.key),
    external: item.external,
    active: isActive(item),
    onPrefetch: !item.external && item.href === "/pages" ? prefetchPages : undefined,
  });

  const renderLink = ({ children, ...props }: SidebarLinkProps) => (
    <ViewTransitionLink {...props}>{children}</ViewTransitionLink>
  );

  const boardSelectorLabels = {
    boardSelector: t("boardSelector"),
    selectBoard: t("selectBoard"),
    unnamedBoard: t("unnamedBoard"),
  };

  return (
    <Sidebar
      labels={{
        mainNavigation: t("mainNavigation"),
        primaryNavigation: t("primaryNavigation"),
        secondaryNavigation: t("secondaryNavigation"),
        navigationMenu: t("navigationMenu"),
        openMenu: t("openMenu"),
        closeMenu: t("closeMenu"),
        expandSidebar: t("expandSidebar"),
        collapseSidebar: t("collapseSidebar"),
        aiAssistant: t("aiAssistant"),
        logoButtonAriaLabel: t("prideCelebrationAriaLabel"),
      }}
      primaryItems={navPrimaryItems.map(toNavItem)}
      secondaryItems={secondaryItems.map(toNavItem)}
      renderLink={renderLink}
      collapsed={collapsed}
      transitioning={transitioning}
      onToggleCollapsed={toggle}
      onTransitionEnd={onTransitionEnd}
      logoIconSrc={appUrl("/icons/favicon-32x32.png")}
      season={season}
      onLogoClick={fireCelebration}
      ai={hasAiProviders ? { active: aiPanelOpen, onOpen: openAiPanel } : undefined}
      boardSelector={
        boards.length > 1 ? (
          <BoardSelector
            boards={boards}
            value={currentBoardId}
            onChange={setCurrentBoardId}
            labels={boardSelectorLabels}
            collapsed={collapsed}
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
          />
        ) : undefined
      }
      renderAccount={({ variant, collapsed: isCollapsed }) =>
        variant === "mobile" ? <SidebarAccount variant="mobile" /> : <SidebarAccount collapsed={isCollapsed} />
      }
      versionSlot={<VersionDisplay />}
      themeToggleSlot={<ThemeToggle />}
      maxWidth={MAX_APP_WIDTH}
      sidebarInset={SIDEBAR_INSET}
    />
  );
}
