"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useUpdate } from "@/components/update-context";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  ArrowUpCircle,
  Loader2,
  Power,
  RefreshCw,
  Cpu,
} from "lucide-react";

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

  const [confirmAction, setConfirmAction] = useState<
    "update" | "restart" | "shutdown" | null
  >(null);
  const [activeOverlay, setActiveOverlay] = useState<
    "restart" | "shutdown" | null
  >(null);

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
    updateMutation.isPending ||
    restartMutation.isPending ||
    shutdownMutation.isPending ||
    !!activeOverlay;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Cpu className="h-4 w-4" />
            System
          </CardTitle>
          <CardDescription>
            Manage FiestaBoard updates and host power.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
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
              {updateAvailable ? "Update Now" : "Re-pull Latest"}
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmAction("restart")}
              disabled={anyPending}
            >
              {restartMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              Restart
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
              Shutdown
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Update confirmation */}
      <Dialog
        open={confirmAction === "update"}
        onOpenChange={(open) => !open && setConfirmAction(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {updateAvailable ? "Update FiestaBoard?" : "Re-pull Latest Image?"}
            </DialogTitle>
            <DialogDescription>
              {updateAvailable
                ? `This will pull v${updateCheck?.latest_version} and recreate the FiestaBoard container. The board display will pause for about 30 seconds and this page will reload automatically.`
                : "This will pull the latest image for the current version and recreate the container. Useful if you want to ensure you're running the newest build of the same version."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmAction(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                setConfirmAction(null);
                updateMutation.mutate();
              }}
            >
              <ArrowUpCircle className="h-4 w-4 mr-2" />
              {updateAvailable ? "Update now" : "Re-pull now"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Restart confirmation */}
      <Dialog
        open={confirmAction === "restart"}
        onOpenChange={(open) => !open && setConfirmAction(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Restart FiestaBoard?</DialogTitle>
            <DialogDescription>
              This will restart the FiestaBoard container. The board display
              will pause for about 5–10 seconds and this page will reload
              automatically.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmAction(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                setConfirmAction(null);
                restartMutation.mutate();
              }}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Restart now
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Shutdown confirmation */}
      <Dialog
        open={confirmAction === "shutdown"}
        onOpenChange={(open) => !open && setConfirmAction(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Shut Down Host?</DialogTitle>
            <DialogDescription>
              This will stop all FiestaBoard services and power off the host
              machine. You will need physical access (or remote SSH) to turn it
              back on.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmAction(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setConfirmAction(null);
                shutdownMutation.mutate();
              }}
            >
              <Power className="h-4 w-4 mr-2" />
              Shut down
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Restarting overlay for plain container restart (not update). */}
      {activeOverlay === "restart" && (
        <RestartingOverlay />
      )}

      {/* Shutdown overlay */}
      {activeOverlay === "shutdown" && (
        <ShutdownOverlay />
      )}
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
function RestartingOverlay({
  currentVersion,
}: {
  currentVersion?: string;
}) {
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
        if (
          currentVersion &&
          v.package_version &&
          v.package_version !== currentVersion
        ) {
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
      <div className="fixed inset-0 z-[100] bg-background/95 backdrop-blur-sm flex items-center justify-center">
        <div className="text-center space-y-4 max-w-sm mx-auto px-4">
          <h2 className="text-xl font-semibold">Taking longer than expected</h2>
          <p className="text-sm text-muted-foreground">
            FiestaBoard may still be restarting. Check the container logs, then
            refresh this page.
          </p>
          <Button variant="outline" onClick={() => window.location.reload()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh page
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-[100] bg-background/95 backdrop-blur-sm flex items-center justify-center">
      <div className="text-center space-y-4">
        <Loader2 className="h-12 w-12 mx-auto animate-spin text-primary" />
        <h2 className="text-xl font-semibold">
          {phase === "restarting" ? "Restarting FiestaBoard…" : "Back online. Reloading…"}
        </h2>
        <p className="text-sm text-muted-foreground">
          {phase === "restarting"
            ? "This will take about 5–10 seconds."
            : "Almost there…"}
        </p>
      </div>
    </div>
  );
}

/**
 * Full-screen overlay shown after a shutdown is initiated.
 * No automatic reload — the host is powering off.
 */
function ShutdownOverlay() {
  return (
    <div className="fixed inset-0 z-[100] bg-background/95 backdrop-blur-sm flex items-center justify-center">
      <div className="text-center space-y-4">
        <Power className="h-12 w-12 mx-auto text-muted-foreground" />
        <h2 className="text-xl font-semibold">Shutting down…</h2>
        <p className="text-sm text-muted-foreground max-w-sm mx-auto">
          FiestaBoard is stopping services and powering off the host. Turn the
          power back on to restart.
        </p>
      </div>
    </div>
  );
}
