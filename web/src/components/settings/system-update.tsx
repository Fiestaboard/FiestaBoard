"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  ArrowUpCircle,
  CheckCircle2,
  ExternalLink,
  Loader2,
  RefreshCw,
  RotateCcw,
  AlertCircle,
  Download,
} from "lucide-react";
import { toast } from "sonner";

export function SystemUpdate() {
  const queryClient = useQueryClient();

  const {
    data: updateCheck,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["update-check"],
    queryFn: () => api.checkForUpdate(),
    staleTime: 1000 * 60 * 60, // Check once per hour
    retry: false,
  });

  const restartMutation = useMutation({
    mutationFn: () => api.restartSystem(),
    onSuccess: (data) => {
      toast.success(data.message);
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to restart container");
    },
  });

  const upgradeMutation = useMutation({
    mutationFn: () => api.upgradeSystem(),
    onSuccess: (data) => {
      toast.success(data.message);
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to upgrade container");
    },
  });

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-3 py-6">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            Checking for updates...
          </span>
        </CardContent>
      </Card>
    );
  }

  if (isError || !updateCheck) {
    return (
      <Card>
        <CardContent className="flex items-center justify-between py-6">
          <div className="flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              Unable to check for updates
            </span>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  const getDisabledReason = (requiresUpdate: boolean) => {
    if (requiresUpdate && !updateCheck?.update_available) return "No update available";
    return undefined;
  };

  return (
    <Card>
      <CardContent className="py-6 space-y-4">
        {/* Version status */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            {updateCheck.update_available ? (
              <ArrowUpCircle className="h-5 w-5 text-amber-500 mt-0.5" />
            ) : (
              <CheckCircle2 className="h-5 w-5 text-green-500 mt-0.5" />
            )}
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">
                  {updateCheck.update_available
                    ? "Update Available"
                    : "Up to Date"}
                </span>
                {updateCheck.update_available && (
                  <Badge variant="secondary" className="text-xs">
                    v{updateCheck.latest_version}
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                {updateCheck.update_available
                  ? `You are running v${updateCheck.current_version}. Version v${updateCheck.latest_version} is available.`
                  : `You are running the latest version (v${updateCheck.current_version}).`}
              </p>
              {updateCheck.error && (
                <p className="text-xs text-muted-foreground">
                  {updateCheck.error}
                </p>
              )}
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 flex-shrink-0"
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ["update-check"] });
            }}
            title="Check for updates"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>

        {/* Container management actions */}
        <div className="flex flex-col gap-3 pt-2 border-t">
          {!updateCheck.is_production && (
            <p className="text-sm text-muted-foreground">
              Container management is only available in production mode.
            </p>
          )}
          {updateCheck.is_production && !updateCheck.docker_connected && (
            <p className="text-sm text-muted-foreground">
              Docker socket is not connected. To enable one-click upgrade and
              restart, mount the Docker socket (
              <code className="text-xs bg-muted px-1 py-0.5 rounded">
                /var/run/docker.sock
              </code>
              ) into the container.
              {updateCheck.update_available && (
                <> You can still upgrade manually by pulling the latest image.</>
              )}
            </p>
          )}
          {updateCheck.is_production && updateCheck.docker_connected && updateCheck.update_available && (
            <p className="text-sm text-muted-foreground">
              If your container is configured with the <code className="text-xs bg-muted px-1 py-0.5 rounded">latest</code> tag, 
              you can pull the newest image and restart automatically.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {updateCheck.is_production && updateCheck.docker_connected && (
              <>
                <Button
                  variant="default"
                  size="sm"
                  onClick={() => upgradeMutation.mutate()}
                  disabled={!updateCheck.update_available || upgradeMutation.isPending || restartMutation.isPending}
                  title={getDisabledReason(true)}
                >
                  {upgradeMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4 mr-2" />
                  )}
                  Pull &amp; Restart
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => restartMutation.mutate()}
                  disabled={restartMutation.isPending || upgradeMutation.isPending}
                  title={getDisabledReason(false)}
                >
                  {restartMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <RotateCcw className="h-4 w-4 mr-2" />
                  )}
                  Restart Only
                </Button>
              </>
            )}
            <Button variant="outline" size="sm" asChild>
              <a
                href={updateCheck.package_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink className="h-4 w-4 mr-2" />
                View Package
              </a>
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
