"use client";

import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpCircle, ExternalLink, RefreshCw } from "lucide-react";
import { useState } from "react";

import { useUpdate } from "@/components/update-context";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

/**
 * Settings → System → Update banner.
 *
 * Behavior:
 *   - If a newer version is available AND the fiestaupdater sidecar is
 *     reachable, show a primary "Update Now" button that triggers an
 *     in-place update.  A blocking overlay polls /version until the
 *     replacement container answers, then reloads.
 *   - If a newer version is available but the sidecar is NOT reachable,
 *     show "View Release" + a small "Enable one-click updates" hint with
 *     copy-paste docker-compose instructions.
 *   - If up to date, render nothing (consistent with prior behavior).
 */
export function SystemUpdate() {
  const t = useTranslations("systemUpdate");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const { startUpdate } = useUpdate();

  const {
    data: updateCheck,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["update-check"],
    queryFn: () => api.checkForUpdate(),
    staleTime: 1000 * 60 * 60,
    retry: false,
  });

  const { data: status } = useQuery({
    queryKey: ["update-status"],
    queryFn: () => api.getUpdateStatus(),
    staleTime: 1000 * 30,
    retry: false,
  });

  const applyMutation = useMutation({
    mutationFn: () => api.applyUpdate(),
    onSuccess: () => startUpdate(updateCheck?.current_version),
  });

  if (isLoading || isError || !updateCheck || !updateCheck.update_available) {
    return null;
  }

  const sidecarReady = !!status?.updater_available;

  return (
    <TooltipProvider>
      <Alert className="border-warning/50 bg-warning/10">
        <ArrowUpCircle className="h-4 w-4 text-warning" />
        <AlertDescription className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium">{t("updateAvailable")}</span>
            <Badge variant="secondary" className="text-xs">
              v{updateCheck.latest_version}
            </Badge>
            <span className="text-sm text-muted-foreground">
              {t("youAreRunning", { currentVersion: updateCheck.current_version })}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" asChild>
              <a href={updateCheck.package_url} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4 mr-2" />
                {t("viewRelease")}
              </a>
            </Button>
            {sidecarReady && (
              <Button size="sm" onClick={() => setConfirmOpen(true)} disabled={applyMutation.isPending}>
                <ArrowUpCircle className="h-4 w-4 mr-2" />
                {t("updateNow")}
              </Button>
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => {
                    queryClient.invalidateQueries({ queryKey: ["update-check"] });
                    queryClient.invalidateQueries({ queryKey: ["update-status"] });
                  }}
                  aria-label={t("checkForUpdates")}
                >
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>{t("checkForUpdates")}</p>
              </TooltipContent>
            </Tooltip>
          </div>
        </AlertDescription>
      </Alert>

      {!sidecarReady && (
        <p className="text-xs text-muted-foreground mt-2 ml-1">
          {t.rich("oneClickHint", {
            profile: () => <span className="font-mono">COMPOSE_PROFILES=fiestaupdater</span>,
            envFile: () => <code>.env</code>,
            command: () => <code>docker compose up -d</code>,
          })}
        </p>
      )}

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("dialogTitle")}</DialogTitle>
            <DialogDescription>
              {t.rich("dialogDescription", {
                version: () => <strong>v{updateCheck.latest_version}</strong>,
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              {tCommon("cancel")}
            </Button>
            <Button
              onClick={() => {
                setConfirmOpen(false);
                applyMutation.mutate();
              }}
            >
              <ArrowUpCircle className="h-4 w-4 mr-2" />
              {t("updateNow")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  );
}
