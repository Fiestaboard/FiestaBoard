"use client";

/**
 * Sign-out button in the sidebar footer. Shown only when auth is on
 * and the user is signed in. Username and password management live in
 * Settings → General → Account — this is just the always-visible
 * escape hatch.
 */

import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

interface SidebarAccountProps {
  /** Whether the parent sidebar is in its collapsed (icon-only) state. */
  collapsed?: boolean;
}

export function SidebarAccount({ collapsed = false }: SidebarAccountProps) {
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

  const button = (
    <button
      type="button"
      onClick={handleSignOut}
      aria-label="Sign out"
      className={cn(
        "flex items-center gap-2 rounded-md py-1.5 text-sm",
        "text-sidebar-foreground/90 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        collapsed ? "w-9 h-9 justify-center" : "w-full px-3",
      )}
    >
      <LogOut className="h-4 w-4 flex-shrink-0" />
      {!collapsed && <span className="font-medium">Sign out</span>}
    </button>
  );

  if (!collapsed) return button;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="right" className="font-medium">
        Sign out
      </TooltipContent>
    </Tooltip>
  );
}
