"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  ArrowUpCircle,
  ExternalLink,
  RefreshCw,
} from "lucide-react";
import ShinyText from "@/components/ui/react-bits/shiny-text";

export function SystemUpdate() {
  const queryClient = useQueryClient();

  const {
    data: updateCheck,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["update-check"],
    queryFn: () => api.checkForUpdate(),
    staleTime: 1000 * 60 * 60, // Check once per hour
    retry: false,
  });

  // Don't render anything while loading, on error, or when up to date
  if (isLoading || isError || !updateCheck || !updateCheck.update_available) {
    return null;
  }

  return (
    <TooltipProvider>
    <Alert className="border-warning/50 bg-warning/10">
      <ArrowUpCircle className="h-4 w-4 text-warning" />
      <AlertDescription className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium"><ShinyText text="Update Available" speed={3} /></span>
          <Badge variant="secondary" className="text-xs">
            v{updateCheck.latest_version}
          </Badge>
          <span className="text-sm text-muted-foreground">
            You are running v{updateCheck.current_version}.
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Button variant="outline" size="sm" asChild>
            <a
              href={updateCheck.package_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              <ExternalLink className="h-4 w-4 mr-2" />
              View Release
            </a>
          </Button>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => {
                  queryClient.invalidateQueries({ queryKey: ["update-check"] });
                }}
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Check for updates</p>
            </TooltipContent>
          </Tooltip>
        </div>
      </AlertDescription>
    </Alert>
    </TooltipProvider>
  );
}
