"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Award,
  Calendar,
  ChevronLeft,
  ChevronRight,
  FileText,
  GalleryHorizontalEnd,
  HelpCircle,
  Home,
  Menu,
  Puzzle,
  Settings,
  Sparkles,
} from "lucide-react";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { FiestaLogo } from "@/components/fiesta-logo";
import { useGlobalAiPanel } from "@/components/global-ai-panel-context";
import { SidebarAccount } from "@/components/sidebar-account";
import { SidebarAurora } from "@/components/sidebar-aurora";
import { SidebarAuroraHorizontal } from "@/components/sidebar-aurora-horizontal";
import { useSidebar } from "@/components/sidebar-context";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { VersionDisplay } from "@/components/version-display";
import { ViewTransitionLink } from "@/components/view-transition-link";
import { usePrefetchPagesData } from "@/hooks/use-board";
import { usePrideActive } from "@/hooks/use-pride-active";
import { type AISettings, api } from "@/lib/api";
import { MAX_APP_WIDTH, SIDEBAR_INSET } from "@/lib/layout-constants";
import { cn } from "@/lib/utils";

interface NavItem {
  key: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  external?: boolean;
}

const primaryItems: NavItem[] = [
  { key: "home", href: "/", icon: Home },
  { key: "pages", href: "/pages", icon: FileText },
  { key: "collections", href: "/collections", icon: GalleryHorizontalEnd },
  { key: "schedule", href: "/schedule", icon: Calendar },
  { key: "integrations", href: "/integrations", icon: Puzzle },
];

const secondaryItems: NavItem[] = [
  { key: "picks", href: "/picks", icon: Award },
  { key: "helpDocs", href: "https://fiestaboard.app/docs/intro", icon: HelpCircle, external: true },
  { key: "settings", href: "/settings", icon: Settings },
];

const PRIDE_COLORS = ["#e40303", "#ff8c00", "#ffed00", "#008026", "#004dff", "#750787"];

export function NavigationSidebar() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [appInset, setAppInset] = useState(0);
  const prefetchPages = usePrefetchPagesData();
  const { collapsed, transitioning, toggle, onTransitionEnd } = useSidebar();
  const t = useTranslations("navigation");
  const { isOpen: aiPanelOpen, open: openAiPanel } = useGlobalAiPanel();

  const isPrideMonth = usePrideActive();

  const firePrideCelebration = useCallback(
    (e: React.MouseEvent) => {
      if (!isPrideMonth) return;
      for (let i = 0; i < 48; i++) {
        const p = document.createElement("div");
        p.className = "pride-burst-particle";
        const angle = (i / 48) * Math.PI * 2 + (Math.random() - 0.5) * 0.5;
        const dist = 80 + Math.random() * 160;
        p.style.setProperty("--tx", `${Math.cos(angle) * dist}px`);
        p.style.setProperty("--ty", `${Math.sin(angle) * dist}px`);
        p.style.setProperty("--rot", `${Math.random() * 720 - 360}deg`);
        p.style.setProperty("--dur", `${0.5 + Math.random() * 0.5}s`);
        p.style.background = PRIDE_COLORS[i % 6];
        p.style.left = `${e.clientX - 3.5}px`;
        p.style.top = `${e.clientY - 3.5}px`;
        document.body.appendChild(p);
        p.addEventListener("animationend", () => p.remove());
      }
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
    [isPrideMonth],
  );

  const { data: aiSettings } = useQuery<AISettings>({
    queryKey: ["ai-settings"],
    queryFn: () => api.getAiSettings(),
  });
  const hasAiProviders = (aiSettings?.enabled ?? false) && (aiSettings?.providers?.length ?? 0) > 0;

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileMenuOpen]);

  useEffect(() => {
    const update = () => setAppInset(Math.max(0, (document.body.clientWidth - MAX_APP_WIDTH) / 2));
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  // Hide the sidebar on auth screens — the user isn't navigating
  // anywhere until they sign in / finish setup, and chrome around
  // the login form makes a fresh install look broken.
  if (pathname.startsWith("/login")) return null;

  const isActive = (item: NavItem) => {
    if (item.external) return false;
    return item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/");
  };

  function renderMobileNavItem(item: NavItem) {
    const active = isActive(item);
    const Icon = item.icon;
    const prefetchHandler = !item.external && item.href === "/pages" ? prefetchPages : undefined;
    const name = t(item.key);
    const mobileClassName = cn(
      "flex items-center gap-3 rounded-lg px-4 py-3 text-base font-medium min-h-[48px]",
      active ? "nav-active font-semibold" : "text-sidebar-foreground nav-active-hover",
    );

    if (item.external) {
      return (
        <a
          key={item.key}
          href={item.href}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => setMobileMenuOpen(false)}
          className={mobileClassName}
        >
          <Icon className="h-5 w-5" />
          {name}
        </a>
      );
    }

    return (
      <ViewTransitionLink
        key={item.key}
        href={item.href!}
        onClick={() => setMobileMenuOpen(false)}
        onMouseEnter={prefetchHandler}
        onFocus={prefetchHandler}
        className={mobileClassName}
      >
        <Icon className="h-5 w-5" />
        {name}
      </ViewTransitionLink>
    );
  }

  function renderDesktopNavItem(item: NavItem) {
    const active = isActive(item);
    const Icon = item.icon;
    const prefetchHandler = !item.external && item.href === "/pages" ? prefetchPages : undefined;
    const name = t(item.key);
    const linkClassName = cn(
      "flex items-center gap-3 py-2 pl-[14px] pr-3 rounded-lg text-sm font-medium transition-colors",
      active ? "nav-active font-semibold" : "text-sidebar-foreground nav-active-hover",
    );

    let link: React.ReactElement;

    if (item.external) {
      link = (
        <a
          href={item.href}
          target="_blank"
          rel="noopener noreferrer"
          className={linkClassName}
          aria-label={collapsed ? name : undefined}
        >
          <Icon className="h-5 w-5 flex-shrink-0" />
          <span
            className={cn(
              "whitespace-nowrap overflow-hidden transition-opacity duration-100",
              collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-48 delay-150",
            )}
          >
            {name}
          </span>
        </a>
      );
    } else {
      link = (
        <ViewTransitionLink
          href={item.href!}
          onMouseEnter={prefetchHandler}
          onFocus={prefetchHandler}
          className={linkClassName}
          aria-label={collapsed ? name : undefined}
        >
          <Icon className="h-5 w-5 flex-shrink-0" />
          <span
            className={cn(
              "whitespace-nowrap overflow-hidden transition-opacity duration-100",
              collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-48 delay-150",
            )}
          >
            {name}
          </span>
        </ViewTransitionLink>
      );
    }

    return (
      <Tooltip key={item.key}>
        <TooltipTrigger asChild>{link}</TooltipTrigger>
        {collapsed && (
          <TooltipContent side="right" className="font-medium">
            {name}
          </TooltipContent>
        )}
      </Tooltip>
    );
  }

  return (
    <>
      {/* Mobile Header */}
      <header className="lg:hidden fixed top-2 left-3 right-3 z-[100] overflow-hidden sidebar-gradient-horizontal">
        {isPrideMonth && <SidebarAuroraHorizontal />}
        <div className="relative z-[1] flex items-center px-4 h-14">
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9 flex-shrink-0 -ml-2 text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label={mobileMenuOpen ? t("closeMenu") : t("openMenu")}
          >
            {mobileMenuOpen ? (
              <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <Menu className="h-6 w-6" />
            )}
          </Button>
          <div
            className={cn("flex items-center gap-3 min-w-0 flex-1 ml-2", isPrideMonth && "cursor-pointer")}
            onClick={isPrideMonth ? firePrideCelebration : undefined}
          >
            <img src="/icons/favicon-32x32.png" alt="" width={32} height={32} className="flex-shrink-0" />
            <FiestaLogo size="sm" className="logo-on-gradient whitespace-nowrap" />
          </div>
        </div>
      </header>

      {/* Mobile Menu Backdrop */}
      <div
        data-testid="mobile-backdrop"
        className={cn(
          "lg:hidden fixed inset-0 z-[90] bg-black/25 backdrop-blur-[2px] transition-opacity duration-200 pointer-events-none",
          mobileMenuOpen ? "opacity-100 pointer-events-auto" : "opacity-0",
        )}
        onClick={() => setMobileMenuOpen(false)}
        aria-hidden="true"
      />

      {/* Mobile Menu */}
      <div
        className={cn(
          "lg:hidden fixed top-[72px] left-3 right-3 z-[95] flex max-h-[calc(100dvh-5.5rem)] flex-col overflow-hidden sidebar-gradient-horizontal",
          mobileMenuOpen ? "opacity-100" : "opacity-0 pointer-events-none",
        )}
        role={mobileMenuOpen ? "dialog" : undefined}
        aria-modal={mobileMenuOpen ? true : undefined}
        aria-label={mobileMenuOpen ? t("navigationMenu") : undefined}
        aria-hidden={!mobileMenuOpen}
        inert={!mobileMenuOpen ? true : undefined}
        style={{
          clipPath: mobileMenuOpen ? "inset(0 0 0 0 round 16px)" : "inset(0 0 100% 0 round 16px)",
          transition: "clip-path 350ms cubic-bezier(0.16, 1, 0.3, 1), opacity 250ms ease",
        }}
      >
        <nav aria-label={t("primaryNavigation")} className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {primaryItems.map(renderMobileNavItem)}
          {hasAiProviders && (
            <button
              type="button"
              onClick={() => {
                openAiPanel();
                setMobileMenuOpen(false);
              }}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg px-4 py-3 text-base font-medium min-h-[48px]",
                aiPanelOpen ? "nav-active font-semibold" : "text-sidebar-foreground nav-active-hover",
              )}
            >
              <Sparkles className="h-5 w-5" />
              {t("aiAssistant")}
            </button>
          )}
        </nav>
        <div className="shrink-0 border-t border-sidebar-border mx-3" />
        <div className="shrink-0 px-3 py-3 text-sidebar-foreground">
          <nav aria-label={t("secondaryNavigation")} className="space-y-1">
            {secondaryItems.map(renderMobileNavItem)}
            <SidebarAccount variant="mobile" />
          </nav>
          <div className="mt-2 flex items-center justify-between gap-2 border-t border-sidebar-border/80 px-4 pt-3">
            <VersionDisplay />
            <ThemeToggle />
          </div>
        </div>
      </div>

      {/* Desktop Sidebar */}
      <TooltipProvider delayDuration={0}>
        <aside
          aria-label={t("mainNavigation")}
          className={cn(
            "hidden lg:fixed lg:top-3 lg:bottom-3 lg:z-50 lg:block sidebar-gradient sidebar-transition",
            collapsed ? "lg:w-16" : "lg:w-64",
            transitioning && "is-transitioning",
          )}
          style={{ left: appInset + SIDEBAR_INSET }}
          onTransitionEnd={(e) => {
            if (e.target === e.currentTarget && e.propertyName === "width") {
              onTransitionEnd();
            }
          }}
        >
          {isPrideMonth && <SidebarAurora />}
          {/* Edge toggle button -- sits on the sidebar border, Jira-style */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={toggle}
                aria-label={collapsed ? t("expandSidebar") : t("collapseSidebar")}
                className="absolute -right-3.5 top-[51px] z-[51] flex h-7 w-7 items-center justify-center rounded-full border border-gray-200 dark:border-gray-700 bg-background text-gray-500 dark:text-gray-400 shadow-md hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
              >
                {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">{collapsed ? t("expandSidebar") : t("collapseSidebar")}</TooltipContent>
          </Tooltip>

          <div className="relative z-[1] flex h-full flex-col overflow-hidden">
            {/* Header */}
            <div
              className={cn("flex items-center gap-2 overflow-hidden px-4 py-4", isPrideMonth && "cursor-pointer")}
              onClick={isPrideMonth ? firePrideCelebration : undefined}
            >
              <img src="/icons/favicon-32x32.png" alt="" width={32} height={32} className="flex-shrink-0" />
              <FiestaLogo
                className={cn(
                  "logo-on-gradient whitespace-nowrap overflow-hidden transition-opacity duration-100",
                  collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-48 delay-150",
                )}
              />
            </div>

            <div className="mx-2 border-t border-sidebar-border" />

            {/* Primary Navigation — flex-1 pins secondary + version row to the bottom */}
            <nav aria-label={t("primaryNavigation")} className="min-h-0 flex-1 space-y-1 overflow-y-auto py-4 px-2">
              {primaryItems.map(renderDesktopNavItem)}
            </nav>

            {hasAiProviders && (
              <>
                <div className="mx-2 border-t border-sidebar-border" />
                <div className="shrink-0 px-2 py-2">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={openAiPanel}
                        aria-label={t("aiAssistant")}
                        className={cn(
                          "flex w-full items-center gap-3 py-2 pl-[14px] pr-3 rounded-lg text-sm font-medium transition-colors",
                          aiPanelOpen ? "nav-active font-semibold" : "text-sidebar-foreground nav-active-hover",
                        )}
                      >
                        <Sparkles className="h-5 w-5 flex-shrink-0" />
                        <span
                          className={cn(
                            "whitespace-nowrap overflow-hidden transition-opacity duration-100",
                            collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-48 delay-150",
                          )}
                        >
                          {t("aiAssistant")}
                        </span>
                      </button>
                    </TooltipTrigger>
                    {collapsed && (
                      <TooltipContent side="right" className="font-medium">
                        {t("aiAssistant")}
                      </TooltipContent>
                    )}
                  </Tooltip>
                </div>
              </>
            )}

            <div className="mx-2 border-t border-sidebar-border" />

            <div className="shrink-0 px-2 pt-2 pb-3">
              <nav aria-label={t("secondaryNavigation")} className="space-y-1">
                {secondaryItems.map(renderDesktopNavItem)}
                <SidebarAccount collapsed={collapsed} />
              </nav>
              <div className="mt-2 flex items-center justify-between gap-2 border-t border-sidebar-border/80 py-2 pl-[14px] pr-3">
                <div
                  className={cn(
                    "min-w-0 overflow-hidden whitespace-nowrap transition-opacity duration-100",
                    collapsed ? "max-w-0 opacity-0" : "max-w-[min(200px,100%)] opacity-100 delay-150",
                  )}
                >
                  <VersionDisplay />
                </div>
                <div className="flex-shrink-0">
                  <ThemeToggle />
                </div>
              </div>
            </div>
          </div>
        </aside>
      </TooltipProvider>
    </>
  );
}
