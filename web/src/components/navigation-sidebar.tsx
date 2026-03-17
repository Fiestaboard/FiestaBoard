"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { Home, FileText, Settings, Calendar, Menu, Puzzle, GalleryHorizontalEnd, ChevronLeft, ChevronRight, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { MAX_APP_WIDTH, SIDEBAR_INSET } from "@/lib/layout-constants";
import { ThemeToggle } from "@/components/theme-toggle";
import { ServiceStatus } from "@/components/service-status";
import { VersionDisplay } from "@/components/version-display";
import { Button } from "@/components/ui/button";
import { ViewTransitionLink } from "@/components/view-transition-link";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { usePrefetchPagesData } from "@/hooks/use-board";
import { FiestaLogo } from "@/components/fiesta-logo";
import { useSidebar } from "@/components/sidebar-context";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const navigationItems = [
  { key: "home" as const, href: "/", icon: Home },
  { key: "pages" as const, href: "/pages", icon: FileText },
  { key: "carousels" as const, href: "/carousels", icon: GalleryHorizontalEnd },
  { key: "schedule" as const, href: "/schedule", icon: Calendar },
  { key: "integrations" as const, href: "/integrations", icon: Puzzle },
  { key: "settings" as const, href: "/settings", icon: Settings },
];

export function NavigationSidebar() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [appInset, setAppInset] = useState(0);
  const prefetchPages = usePrefetchPagesData();
  const { collapsed, transitioning, toggle, onTransitionEnd } = useSidebar();
  const t = useTranslations("navigation");

  const debugEnabledQuery = useQuery({
    queryKey: ["debug-monitor", "enabled"],
    queryFn: api.getDebugMonitorEnabled,
    staleTime: 60_000,
    retry: 1,
  });

  const grafanaUrl = "/grafana/";

  type NavItem = { key: string; href: string; icon: typeof Home; external?: boolean };
  const navItems: NavItem[] = debugEnabledQuery.data?.enabled
    ? [...navigationItems, { key: "monitor", href: grafanaUrl, icon: Activity, external: true }]
    : navigationItems;

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

  return (
    <>
      {/* Mobile Header */}
      <header className="lg:hidden fixed top-2 left-3 right-3 z-[100] sidebar-gradient-horizontal">
        <div className="flex items-center px-4 h-14">
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
          <div className="flex items-center gap-3 min-w-0 flex-1 ml-2">
            <Image
              src="/icons/favicon-32x32.png"
              alt="FiestaBoard"
              width={32}
              height={32}
              className="flex-shrink-0"
            />
            <FiestaLogo size="sm" className="whitespace-nowrap" />
          </div>
          <div className="ml-3">
            <ServiceStatus />
          </div>
        </div>
      </header>

      {/* Mobile Menu Backdrop */}
      <div 
        className={cn(
          "lg:hidden fixed inset-0 z-[90] bg-black/25 backdrop-blur-[2px] transition-opacity duration-200 pointer-events-none",
          mobileMenuOpen ? "opacity-100 pointer-events-auto" : "opacity-0"
        )}
        onClick={() => setMobileMenuOpen(false)}
        aria-hidden="true"
      />

      {/* Mobile Menu */}
      <div 
        className={cn(
          "lg:hidden fixed top-[72px] left-3 right-3 z-[95] sidebar-gradient-horizontal",
          mobileMenuOpen
            ? "opacity-100"
            : "opacity-0 pointer-events-none"
        )}
        role="dialog"
        aria-modal={mobileMenuOpen}
        aria-label="Navigation menu"
        aria-hidden={!mobileMenuOpen}
        style={{
          clipPath: mobileMenuOpen ? 'inset(0 0 0 0 round 16px)' : 'inset(0 0 100% 0 round 16px)',
          transition: 'clip-path 350ms cubic-bezier(0.16, 1, 0.3, 1), opacity 250ms ease',
        }}
      >
        <nav aria-label="Mobile navigation" className="space-y-1 px-3 py-4">
          {navItems.map((item) => {
            const isActive = !item.external && (item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/"));
            const Icon = item.icon;
            const prefetchHandler = !item.external && item.href === "/pages" ? prefetchPages : undefined;
            const name = item.external ? item.key.charAt(0).toUpperCase() + item.key.slice(1) : t(item.key);
            const mobileClassName = cn(
              "flex items-center gap-3 rounded-lg px-4 py-3 text-base font-medium min-h-[48px]",
              isActive
                ? "bg-sidebar-accent text-sidebar-accent-foreground font-semibold"
                : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground active:bg-sidebar-accent"
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
                key={item.href}
                href={item.href}
                onClick={() => setMobileMenuOpen(false)}
                onMouseEnter={prefetchHandler}
                onFocus={prefetchHandler}
                className={mobileClassName}
              >
                <Icon className="h-5 w-5" />
                {name}
              </ViewTransitionLink>
            );
          })}
        </nav>
        <div className="border-t border-sidebar-border px-4 py-3 flex items-center justify-between text-sidebar-foreground">
          <VersionDisplay />
          <ThemeToggle />
        </div>
      </div>

      {/* Desktop Sidebar */}
      <TooltipProvider delayDuration={0}>
        <aside
          className={cn(
            "hidden lg:fixed lg:top-3 lg:bottom-3 lg:z-50 lg:block sidebar-gradient sidebar-transition",
            collapsed ? "lg:w-16" : "lg:w-64",
            transitioning && "is-transitioning"
          )}
          style={{ left: appInset + SIDEBAR_INSET }}
          onTransitionEnd={(e) => {
            if (e.target === e.currentTarget && e.propertyName === "width") {
              onTransitionEnd();
            }
          }}
        >
          {/* Edge toggle button -- sits on the sidebar border, Jira-style */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={toggle}
                aria-label={collapsed ? t("expandSidebar") : t("collapseSidebar")}
                className="absolute -right-3.5 top-[51px] z-[51] flex h-7 w-7 items-center justify-center rounded-full border border-gray-200 dark:border-gray-700 bg-background text-gray-500 dark:text-gray-400 shadow-md hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
              >
                {collapsed ? (
                  <ChevronRight className="h-3.5 w-3.5" />
                ) : (
                  <ChevronLeft className="h-3.5 w-3.5" />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">
              {collapsed ? t("expandSidebar") : t("collapseSidebar")}
            </TooltipContent>
          </Tooltip>

          <div className="flex h-full flex-col overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-sidebar-border overflow-hidden px-4 py-4">
              <div className="flex items-center gap-2 flex-shrink-0">
                <Image
                  src="/icons/favicon-32x32.png"
                  alt="FiestaBoard"
                  width={32}
                  height={32}
                  className="flex-shrink-0"
                />
                <FiestaLogo className={cn(
                  "whitespace-nowrap overflow-hidden transition-opacity duration-100",
                  collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-48 delay-150",
                )} />
              </div>
              <div className={cn(
                "overflow-hidden flex-shrink-0 transition-opacity duration-100",
                collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-[200px] delay-150",
              )}>
                <ServiceStatus />
              </div>
            </div>

            {/* Navigation */}
            <nav aria-label="Main navigation" className="flex-1 space-y-1 py-4 px-2">
              {navItems.map((item) => {
                const isActive = !item.external && (item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/"));
                const Icon = item.icon;
                const prefetchHandler = !item.external && item.href === "/pages" ? prefetchPages : undefined;
                const name = item.external ? item.key.charAt(0).toUpperCase() + item.key.slice(1) : t(item.key);
                const linkClassName = cn(
                  "flex items-center gap-3 py-2 pl-[14px] pr-3 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-semibold"
                    : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                );

                const link = item.external ? (
                  <a
                    href={item.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={linkClassName}
                    aria-label={collapsed ? name : undefined}
                  >
                    <Icon className="h-5 w-5 flex-shrink-0" />
                    <span className={cn(
                      "whitespace-nowrap overflow-hidden transition-opacity duration-100",
                      collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-48 delay-150",
                    )}>{name}</span>
                  </a>
                ) : (
                  <ViewTransitionLink
                    href={item.href}
                    onMouseEnter={prefetchHandler}
                    onFocus={prefetchHandler}
                    className={linkClassName}
                    aria-label={collapsed ? name : undefined}
                  >
                    <Icon className="h-5 w-5 flex-shrink-0" />
                    <span className={cn(
                      "whitespace-nowrap overflow-hidden transition-opacity duration-100",
                      collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-48 delay-150",
                    )}>{name}</span>
                  </ViewTransitionLink>
                );

                return (
                  <Tooltip key={item.external ? item.key : item.href}>
                    <TooltipTrigger asChild>
                      {link}
                    </TooltipTrigger>
                    {collapsed && (
                      <TooltipContent side="right" className="font-medium">
                        {name}
                      </TooltipContent>
                    )}
                  </Tooltip>
                );
              })}
            </nav>

            {/* Footer */}
            <div className="border-t border-sidebar-border px-4 py-3 flex items-center justify-between">
              <div className={cn(
                "overflow-hidden whitespace-nowrap transition-opacity duration-100 min-w-0",
                collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-[200px] delay-150",
              )}><VersionDisplay /></div>
              <div className="flex-shrink-0"><ThemeToggle /></div>
            </div>
          </div>
        </aside>
      </TooltipProvider>
    </>
  );
}
