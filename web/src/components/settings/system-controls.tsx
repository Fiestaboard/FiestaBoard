"use client";

import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Heading,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUpCircle, Cpu, Loader2, Power, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { useUpdate } from "@/components/update-context";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

/**
 * Settings → System Controls card.
 *
 * Always visible when the fiestaupdater sidecar is reachable.
 * Shows three actions:
 *   - Update Now: pull the latest image and recreate the container
 *   - Restart:    restart just the fiestaboard container
 *   - Shutdown:   gracefully stop services and power off the host
 *
 * Each action shows a confirmation dialog before proceeding.
 * Restart shows a full-screen overlay while the container comes back.
 * Shutdown shows a final "shutting down" screen (no automatic reload).
 */
export function SystemControls() {
  const t = useTranslations("systemControls");
  const tCommon = useTranslations("common");
  const { data: status, isLoading } = useQuery({
    queryKey: ["update-status"],
    queryFn: () => api.getUpdateStatus(),
    staleTime: 1000 * 30,
    retry: false,
  });

  const { data: updateCheck } = useQuery({
    queryKey: ["update-check"],
    queryFn: () => api.checkForUpdate(),
    staleTime: 1000 * 60 * 60,
    retry: false,
  });

  const [confirmAction, setConfirmAction] = useState<"update" | "restart" | "shutdown" | null>(null);
  const [activeOverlay, setActiveOverlay] = useState<"restart" | "shutdown" | null>(null);

  const { startUpdate } = useUpdate();

  const updateMutation = useMutation({
    mutationFn: () => api.applyUpdate(),
    onSuccess: () => startUpdate(updateCheck?.current_version),
  });

  const restartMutation = useMutation({
    mutationFn: () => api.restartSystem(),
    onSuccess: () => setActiveOverlay("restart"),
  });

  const shutdownMutation = useMutation({
    mutationFn: () => api.shutdownSystem(),
    onSuccess: () => setActiveOverlay("shutdown"),
  });

  if (isLoading || !status?.updater_available) {
    return null;
  }

  const updateAvailable = !!updateCheck?.update_available;
  const anyPending =
    updateMutation.isPending || restartMutation.isPending || shutdownMutation.isPending || !!activeOverlay;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Cpu className="h-4 w-4" />
            {t("title")}
          </CardTitle>
          <CardDescription>{t("description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <Flex wrap gap="2">
            <Button
              variant={updateAvailable ? "default" : "outline"}
              size="sm"
              onClick={() => setConfirmAction("update")}
              disabled={anyPending}
            >
              {updateMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <ArrowUpCircle className="h-4 w-4 mr-2" />
              )}
              {updateAvailable ? t("updateNow") : t("rePullLatest")}
            </Button>

            <Button variant="outline" size="sm" onClick={() => setConfirmAction("restart")} disabled={anyPending}>
              {restartMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              {t("restart")}
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmAction("shutdown")}
              disabled={anyPending}
              className="text-destructive hover:text-destructive"
            >
              {shutdownMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Power className="h-4 w-4 mr-2" />
              )}
              {t("shutdown")}
            </Button>
          </Flex>
        </CardContent>
      </Card>

      {/* Update confirmation */}
      <Dialog open={confirmAction === "update"} onOpenChange={(open) => !open && setConfirmAction(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{updateAvailable ? t("updateDialogTitle") : t("rePullDialogTitle")}</DialogTitle>
            <DialogDescription>
              {updateAvailable
                ? t("updateDialogDescription", { version: updateCheck?.latest_version ?? "" })
                : t("rePullDialogDescription")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmAction(null)}>
              {tCommon("cancel")}
            </Button>
            <Button
              onClick={() => {
                setConfirmAction(null);
                updateMutation.mutate();
              }}
            >
              <ArrowUpCircle className="h-4 w-4 mr-2" />
              {updateAvailable ? t("updateNow") : t("rePullNow")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Restart confirmation */}
      <Dialog open={confirmAction === "restart"} onOpenChange={(open) => !open && setConfirmAction(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("restartDialogTitle")}</DialogTitle>
            <DialogDescription>{t("restartDialogDescription")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmAction(null)}>
              {tCommon("cancel")}
            </Button>
            <Button
              onClick={() => {
                setConfirmAction(null);
                restartMutation.mutate();
              }}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              {t("restartNow")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Shutdown confirmation */}
      <Dialog open={confirmAction === "shutdown"} onOpenChange={(open) => !open && setConfirmAction(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("shutdownDialogTitle")}</DialogTitle>
            <DialogDescription>{t("shutdownDialogDescription")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmAction(null)}>
              {tCommon("cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setConfirmAction(null);
                shutdownMutation.mutate();
              }}
            >
              <Power className="h-4 w-4 mr-2" />
              {t("shutdownConfirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Restarting overlay for plain container restart (not update). */}
      {activeOverlay === "restart" && <RestartingOverlay />}

      {/* Shutdown overlay */}
      {activeOverlay === "shutdown" && <ShutdownOverlay />}
    </>
  );
}

// Timeout before showing the "something went wrong" error state.
const RESTART_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Full-screen overlay shown while the container restarts (restart or update).
 *
 * For updates the old container keeps running during the image pull, so a
 * naive "poll until /version responds" would reload the page immediately
 * against the still-running old container.  Instead we use a two-phase
 * approach:
 *
 *   Phase 1 (restarting): poll every 2 s.  Wait until the API goes DOWN
 *     (catch) OR until a version change is detected (if currentVersion is
 *     provided).  Track everWentDown so phase 2 knows a real restart began.
 *   Phase 2 (back up): poll every 2 s.  Once the API responds successfully
 *     after having been down, reload.
 *
 * A 5-minute timeout surfaces an error state with a manual refresh button
 * so the user is never stuck in an infinite spinner.
 */
function RestartingOverlay({ currentVersion }: { currentVersion?: string }) {
  const t = useTranslations("systemControls");
  const [phase, setPhase] = useState<"restarting" | "ready" | "error">("restarting");

  useEffect(() => {
    let cancelled = false;
    let everWentDown = false;
    const deadline = Date.now() + RESTART_TIMEOUT_MS;

    const tick = async () => {
      if (cancelled) return;
      if (Date.now() >= deadline) {
        setPhase("error");
        return;
      }
      try {
        const v = await api.getVersion();
        if (everWentDown) {
          // Container came back after a real restart — reload.
          if (!cancelled) {
            setPhase("ready");
            setTimeout(() => window.location.reload(), 800);
          }
          return;
        }
        // Container is still running.  If a version change is detected
        // (e.g. image was swapped without a visible down period), reload.
        if (currentVersion && v.package_version && v.package_version !== currentVersion) {
          if (!cancelled) {
            setPhase("ready");
            setTimeout(() => window.location.reload(), 800);
          }
          return;
        }
      } catch {
        // API is down — the container stopped.  Start watching for it to
        // come back.
        everWentDown = true;
      }
      setTimeout(tick, 2000);
    };

    // Brief initial pause before the first poll.  This lets Docker process
    // the restart/update command so the container has a chance to stop
    // before we begin checking.
    setTimeout(tick, 1500);
    return () => {
      cancelled = true;
    };
  }, [currentVersion]);

  if (phase === "error") {
    return (
      <Flex align="center" justify="center" className="fixed inset-0 z-[100] bg-background/95 backdrop-blur-sm">
        <Stack gap="4" className="text-center max-w-sm mx-auto px-4">
          <Heading level={2} size="xl">
            {t("takingLonger")}
          </Heading>
          <Text tone="muted">{t("takingLongerDescription")}</Text>
          <Button variant="outline" onClick={() => window.location.reload()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            {t("refreshPage")}
          </Button>
        </Stack>
      </Flex>
    );
  }

  return (
    <Flex align="center" justify="center" className="fixed inset-0 z-[100] bg-background/95 backdrop-blur-sm">
      <Stack gap="4" className="text-center">
        <Loader2 className="h-12 w-12 mx-auto animate-spin text-primary" />
        <Heading level={2} size="xl">
          {phase === "restarting" ? t("restartingFiestaboard") : t("backOnline")}
        </Heading>
        <Text tone="muted">{phase === "restarting" ? t("restartingDuration") : t("almostThere")}</Text>
      </Stack>
    </Flex>
  );
}

/**
 * Full-screen overlay shown after a shutdown is initiated.
 * No automatic reload — the host is powering off.
 */
function ShutdownOverlay() {
  const t = useTranslations("systemControls");
  return (
    <Flex align="center" justify="center" className="fixed inset-0 z-[100] bg-background/95 backdrop-blur-sm">
      <Stack gap="4" className="text-center">
        <Power className="h-12 w-12 mx-auto text-muted-foreground" />
        <Heading level={2} size="xl">
          {t("shuttingDown")}
        </Heading>
        <Text tone="muted" className="max-w-sm mx-auto">
          {t("shuttingDownDescription")}
        </Text>
      </Stack>
    </Flex>
  );
}
