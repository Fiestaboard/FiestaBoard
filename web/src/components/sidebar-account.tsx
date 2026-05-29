"use client";

/**
 * Account pill rendered in the sidebar footer when auth is on and the
 * user is signed in. Gives users an always-visible place to sign out
 * (otherwise the only sign-out lived inside Settings → General →
 * Account, which is impossible to find).
 *
 * Hides itself entirely when auth is disabled so local-only installs
 * see no extra chrome.
 */

import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOut, UserCircle2 } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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

  const username = authStatus.username ?? "";

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

  const trigger = (
    <button
      type="button"
      aria-label={`Account menu for ${username}`}
      className={cn(
        "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm",
        "text-sidebar-foreground/90 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        collapsed && "justify-center",
      )}
    >
      <UserCircle2 className="h-4 w-4 flex-shrink-0" />
      {!collapsed && (
        <span className="truncate max-w-[140px] font-medium">{username}</span>
      )}
    </button>
  );

  return (
    <DropdownMenu>
      {collapsed ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="right" className="font-medium">
            Signed in as {username}
          </TooltipContent>
        </Tooltip>
      ) : (
        <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
      )}
      <DropdownMenuContent align="end" side="top" className="w-56">
        <DropdownMenuLabel className="flex items-center gap-2">
          <UserCircle2 className="h-4 w-4 text-muted-foreground" />
          <span className="truncate">{username}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={handleSignOut} className="cursor-pointer">
          <LogOut className="h-4 w-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
