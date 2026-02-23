"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Package, ArrowUpCircle } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function VersionDisplay() {
  const { data: version } = useQuery({
    queryKey: ["version"],
    queryFn: () => api.getVersion(),
    staleTime: Infinity, // Version doesn't change often
    retry: false,
  });

  const { data: updateCheck } = useQuery({
    queryKey: ["update-check"],
    queryFn: () => api.checkForUpdate(),
    staleTime: 1000 * 60 * 60, // Check once per hour
    retry: false,
  });

  if (!version) return null;

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <Package className="h-3 w-3" />
      <span suppressHydrationWarning>
        v{version.package_version}
        {version.is_dev && " (dev)"}
      </span>
      {updateCheck?.update_available && (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <ArrowUpCircle className="h-3.5 w-3.5 text-amber-500" />
            </TooltipTrigger>
            <TooltipContent>
              <p>Update available: v{updateCheck.latest_version}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  );
}

