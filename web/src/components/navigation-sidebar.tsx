"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { Home, FileText, Settings, Calendar, Menu, X, Puzzle } from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";
import { ServiceStatus } from "@/components/service-status";
import { VersionDisplay } from "@/components/version-display";
import { Button } from "@/components/ui/button";
import { ViewTransitionLink } from "@/components/view-transition-link";

const navigation = [
  {
    name: "Home",
    href: "/",
    icon: Home,
  },
  {
    name: "Pages",
    href: "/pages",
    icon: FileText,
  },
  {
    name: "Schedule",
    href: "/schedule",
    icon: Calendar,
  },
  {
    name: "Integrations",
    href: "/integrations",
    icon: Puzzle,
  },
  {
    name: "Settings",
    href: "/settings",
    icon: Settings,
  },
];

export function NavigationSidebar() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  // Prevent body scroll when mobile menu is open
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
              <X className="h-6 w-6 text-foreground" />
            ) : (
              <Menu className="h-6 w-6 text-foreground" />
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

      {/* Mobile Menu - Always rendered but transformed off-screen */}
      <div 
        className={cn(
          "lg:hidden fixed top-14 left-0 right-0 z-[95] bg-background border-b shadow-lg",
          "transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          mobileMenuOpen ? "translate-y-0" : "-translate-y-full"
        )}
        style={{
          // Force GPU acceleration and prevent flash
          willChange: 'transform',
          backfaceVisibility: 'hidden',
          transform: mobileMenuOpen ? 'translate3d(0, 0, 0)' : 'translate3d(0, -100%, 0)',
        }}
      >
        <nav className="space-y-1 px-3 py-4">
          {navigation.map((item) => {
            const isActive = item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/");
            const Icon = item.icon;

            return (
              <ViewTransitionLink
                key={item.href}
                href={item.href}
                onClick={() => setMobileMenuOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-4 py-3 text-base font-medium min-h-[48px]",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground active:bg-accent"
                )}
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
      <aside className="hidden lg:fixed lg:inset-y-0 lg:left-0 lg:z-50 lg:block lg:w-64 lg:border-r lg:bg-background">
        <div className="flex h-full flex-col">
          {/* Header */}
          <div className="flex items-center justify-between border-b px-6 py-4">
            <div className="flex items-center gap-2">
              <Image
                src="/icons/favicon-32x32.png"
                alt="FiestaBoard"
                width={32}
                height={32}
                className="flex-shrink-0"
              />
              <h1 className="text-xl font-semibold tracking-tight">FiestaBoard</h1>
            </div>
            <ServiceStatus />
          </div>

          {/* Navigation */}
          <nav className="flex-1 space-y-1 px-3 py-4">
            {navigation.map((item) => {
              const isActive = item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/");
              const Icon = item.icon;

              return (
                <ViewTransitionLink
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )}
                >
                  <Icon className="h-5 w-5" />
                  {item.name}
                </ViewTransitionLink>
              );
            })}
          </nav>

          {/* Footer */}
          <div className="border-t px-6 py-4 flex items-center justify-between">
            <VersionDisplay />
            <ThemeToggle />
          </div>
        </div>
      </aside>
    </>
  );
}

