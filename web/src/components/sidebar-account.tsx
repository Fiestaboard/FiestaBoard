"use client";

/**
 * Sign-out button in the sidebar footer. Shown only when auth is on
 * and the user is signed in. Styled to match the surrounding nav
 * items exactly so it doesn't read as a different control type.
 *
 * Username and password management live in Settings → General →
 * Account — this is just the always-visible escape hatch.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface SidebarAccountProps {
  /** Whether the parent sidebar is in its collapsed (icon-only) state. */
  collapsed?: boolean;
  /** Render at mobile-drawer scale (larger touch target) instead of desktop. */
  variant?: "desktop" | "mobile";
}

export function SidebarAccount({ collapsed = false, variant = "desktop" }: SidebarAccountProps) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: authStatus } = useQuery({
    queryKey: ["auth-status"],
    queryFn: api.getAuthStatus,
    staleTime: 30_000,
    retry: false,
  });

  if (!authStatus?.enabled || !authStatus.authenticated) {
    return null;
  }

  const handleSignOut = async () => {
    try {
      await api.logout();
    } catch {
      // Best-effort — the server cookie clear may fail but we still
      // want to drop the client cache and bounce to /login.
    }
    queryClient.removeQueries({ queryKey: ["auth-status"] });
    router.replace("/login");
  };

  // Class names mirror renderDesktopNavItem / renderMobileNavItem in
  // navigation-sidebar.tsx so the button reads as a peer of the nav
  // links rather than a one-off control.
  const className = cn(
    "flex w-full items-center gap-3 rounded-lg font-medium transition-colors",
    "text-sidebar-foreground nav-active-hover",
    variant === "mobile" ? "px-4 py-3 text-base min-h-[48px]" : "py-2 pl-[14px] pr-3 text-sm",
  );

  const button = (
    <button type="button" onClick={handleSignOut} aria-label="Sign out" className={className}>
      <LogOut className="h-5 w-5 flex-shrink-0" />
      <span
        className={cn(
          "whitespace-nowrap overflow-hidden transition-opacity duration-100",
          collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-48 delay-150",
        )}
      >
        Sign out
      </span>
    </button>
  );

  if (variant === "mobile" || !collapsed) return button;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="right" className="font-medium">
        Sign out
      </TooltipContent>
    </Tooltip>
  );
}
