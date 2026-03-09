"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { Home, FileText, Settings, Calendar, Menu, Puzzle, GalleryHorizontalEnd, ChevronLeft, ChevronRight, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";
import { ServiceStatus } from "@/components/service-status";
import { VersionDisplay } from "@/components/version-display";
import { Button } from "@/components/ui/button";
import { ViewTransitionLink } from "@/components/view-transition-link";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { usePrefetchPagesData } from "@/hooks/use-board";
import { useSidebar } from "@/components/sidebar-context";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const navigation = [
  { name: "Home", href: "/", icon: Home },
  { name: "Pages", href: "/pages", icon: FileText },
  { name: "Carousels", href: "/carousels", icon: GalleryHorizontalEnd },
  { name: "Schedule", href: "/schedule", icon: Calendar },
  { name: "Integrations", href: "/integrations", icon: Puzzle },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function NavigationSidebar() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const prefetchPages = usePrefetchPagesData();
  const { collapsed, transitioning, toggle, onTransitionEnd } = useSidebar();

  const debugEnabledQuery = useQuery({
    queryKey: ["debug-monitor", "enabled"],
    queryFn: api.getDebugMonitorEnabled,
    staleTime: 60_000,
    retry: 1,
  });

  const grafanaUrl =
    typeof window !== "undefined"
      ? `${window.location.protocol}//${window.location.hostname}:3030`
      : "#";

  const navItems = debugEnabledQuery.data?.enabled
    ? [...navigation, { name: "Monitor", href: grafanaUrl, icon: Activity, external: true }]
    : navigation;

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

  return (
    <>
      {/* Mobile Header */}
      <header className="lg:hidden fixed top-0 left-0 right-0 z-[100] border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="flex items-center px-4 h-14">
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9 flex-shrink-0 -ml-2"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
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
            <h1 className="text-lg font-semibold tracking-tight whitespace-nowrap truncate">FiestaBoard</h1>
          </div>
          <div className="ml-3">
            <ServiceStatus />
          </div>
        </div>
      </header>

      {/* Mobile Menu Backdrop */}
      <div 
        className={cn(
          "lg:hidden fixed inset-0 z-[90] bg-background/80 backdrop-blur-sm transition-opacity duration-200 pointer-events-none",
          mobileMenuOpen ? "opacity-100 pointer-events-auto" : "opacity-0"
        )}
        onClick={() => setMobileMenuOpen(false)}
        aria-hidden="true"
      />

      {/* Mobile Menu */}
      <div 
        className={cn(
          "lg:hidden fixed top-14 left-0 right-0 z-[95] bg-background border-b shadow-lg",
          "transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          mobileMenuOpen ? "translate-y-0" : "-translate-y-full"
        )}
        role="dialog"
        aria-modal={mobileMenuOpen}
        aria-label="Navigation menu"
        aria-hidden={!mobileMenuOpen}
        style={{
          contain: 'layout style paint',
          backfaceVisibility: 'hidden',
        }}
      >
        <nav aria-label="Mobile navigation" className="space-y-1 px-3 py-4">
          {navItems.map((item) => {
            const isActive = !item.external && (item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/"));
            const Icon = item.icon;
            const prefetchHandler = !item.external && item.href === "/pages" ? prefetchPages : undefined;
            const className = cn(
              "flex items-center gap-3 rounded-lg px-4 py-3 text-base font-medium min-h-[48px]",
              isActive
                ? "bg-brand-emphasis text-brand-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground active:bg-accent"
            );

            if (item.external) {
              return (
                <a
                  key={item.name}
                  href={item.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setMobileMenuOpen(false)}
                  className={className}
                >
                  <Icon className="h-5 w-5" />
                  {item.name}
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
                className={className}
              >
                <Icon className="h-5 w-5" />
                {item.name}
              </ViewTransitionLink>
            );
          })}
        </nav>
        <div className="border-t px-4 py-3 flex items-center justify-between">
          <VersionDisplay />
          <ThemeToggle />
        </div>
      </div>

      {/* Desktop Sidebar */}
      <TooltipProvider delayDuration={0}>
        <aside
          className={cn(
            "hidden lg:fixed lg:inset-y-0 lg:left-0 lg:z-50 lg:block lg:border-r lg:bg-sidebar border-sidebar-border sidebar-transition",
            collapsed ? "lg:w-16" : "lg:w-64",
            transitioning && "is-transitioning"
          )}
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
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                className="absolute -right-3.5 top-[84px] z-[51] flex h-7 w-7 items-center justify-center rounded-full border bg-background text-muted-foreground shadow-md ring-1 ring-black/[0.08] dark:ring-white/20 hover:bg-accent hover:text-foreground transition-colors"
              >
                {collapsed ? (
                  <ChevronRight className="h-3.5 w-3.5" />
                ) : (
                  <ChevronLeft className="h-3.5 w-3.5" />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">
              {collapsed ? "Expand sidebar" : "Collapse sidebar"}
            </TooltipContent>
          </Tooltip>

          <div className="flex h-full flex-col overflow-hidden">
            {/* Header */}
            <div className={cn(
              "flex items-center border-b border-sidebar-border overflow-hidden",
              collapsed ? "justify-center px-2 py-4" : "justify-between px-6 py-4"
            )}>
              <div className="flex items-center gap-2 flex-shrink-0">
                <Image
                  src="/icons/favicon-32x32.png"
                  alt="FiestaBoard"
                  width={32}
                  height={32}
                  className="flex-shrink-0"
                />
                <h1 className={cn(
                  "text-xl font-semibold tracking-tight whitespace-nowrap",
                  collapsed && "sr-only"
                )}>FiestaBoard</h1>
              </div>
              <div className={cn(collapsed && "sr-only")}>
                <ServiceStatus />
              </div>
            </div>

            {/* Navigation */}
            <nav aria-label="Main navigation" className={cn("flex-1 space-y-1 py-4", collapsed ? "px-2" : "px-3")}>
              {navItems.map((item) => {
                const isActive = !item.external && (item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/"));
                const Icon = item.icon;
                const prefetchHandler = !item.external && item.href === "/pages" ? prefetchPages : undefined;
                const linkClassName = cn(
                  "flex items-center rounded-lg text-sm font-medium",
                  collapsed ? "justify-center p-2" : "gap-3 px-3 py-2",
                  isActive
                    ? "bg-brand-emphasis text-brand-foreground"
                    : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                );

                const link = item.external ? (
                  <a
                    href={item.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={linkClassName}
                    aria-label={collapsed ? item.name : undefined}
                  >
                    <Icon className="h-5 w-5 flex-shrink-0" />
                    <span className={cn(collapsed && "sr-only")}>{item.name}</span>
                  </a>
                ) : (
                  <ViewTransitionLink
                    href={item.href}
                    onMouseEnter={prefetchHandler}
                    onFocus={prefetchHandler}
                    className={linkClassName}
                    aria-label={collapsed ? item.name : undefined}
                  >
                    <Icon className="h-5 w-5 flex-shrink-0" />
                    <span className={cn(collapsed && "sr-only")}>{item.name}</span>
                  </ViewTransitionLink>
                );

                return (
                  <Tooltip key={item.external ? item.name : item.href}>
                    <TooltipTrigger asChild>
                      {link}
                    </TooltipTrigger>
                    {collapsed && (
                      <TooltipContent side="right" className="font-medium">
                        {item.name}
                      </TooltipContent>
                    )}
                  </Tooltip>
                );
              })}
            </nav>

            {/* Footer */}
            <div className={cn(
              "border-t border-sidebar-border",
              collapsed ? "px-2 py-3 flex flex-col items-center gap-2" : "px-6 py-4 flex items-center justify-between"
            )}>
              <div className={cn(collapsed && "sr-only")}><VersionDisplay /></div>
              <ThemeToggle />
            </div>
          </div>
        </aside>
      </TooltipProvider>
    </>
  );
}
