"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FlaskConical, Loader2, Lock, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

/**
 * Settings → Beta section.
 *
 * Currently exposes a single experimental toggle: HTTPS (Beta).
 *
 * Behaviour:
 *   - Toggling ON persists the preference and eagerly generates a
 *     self-signed cert into data/certs/. nginx only switches over on
 *     the next container restart, so we prompt the user to restart.
 *   - Toggling OFF deletes the cert files and again prompts a restart
 *     so nginx falls back to plain HTTP.
 *   - When the fiestaupdater sidecar is reachable we offer a one-click
 *     Restart Now button. Otherwise we show instructions.
 */
export function BetaSettings() {
  const t = useTranslations("betaSettings");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "beta"],
    queryFn: () => api.getBetaSettings(),
    // Refresh on focus so cert status stays current after a restart.
    refetchOnWindowFocus: true,
  });

  const [restartPrompt, setRestartPrompt] = useState<"enabled" | "disabled" | null>(null);
  const [restarting, setRestarting] = useState(false);

  const mutation = useMutation({
    mutationFn: (next: boolean) => api.updateBetaSettings({ https_enabled: next }),
    onSuccess: (resp, variables) => {
      queryClient.invalidateQueries({ queryKey: ["settings", "beta"] });
      queryClient.invalidateQueries({ queryKey: ["settings", "all"] });
      if (resp.cert_error) {
        toast.error(t("certErrorToast", { error: resp.cert_error }));
        return;
      }
      if (resp.restart_required) {
        setRestartPrompt(variables ? "enabled" : "disabled");
      } else {
        toast.success(t("savedToast"));
      }
    },
    onError: (err: Error) => {
      toast.error(t("saveFailedToast", { error: err.message }));
    },
  });

  const restartMutation = useMutation({
    mutationFn: () => api.restartSystem(),
    onSuccess: () => {
      setRestarting(true);
      // Mirror the system-controls flow: hand off to a full-page reload
      // attempt after the container comes back. We keep this simple --
      // the user can just refresh manually if it doesn't auto-recover.
      setTimeout(() => window.location.reload(), 8000);
    },
    onError: (err: Error) => {
      toast.error(t("restartFailedToast", { error: err.message }));
    },
  });

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <FlaskConical className="h-4 w-4" />
            {t("title")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  const httpsEnabled = data.settings.https_enabled;
  const certPresent = data.https.cert_present;
  const updaterAvailable = data.https.updater_available;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <FlaskConical className="h-4 w-4" />
            {t("title")}
            <Badge variant="outline" className="ml-1 text-[10px] uppercase tracking-wide">
              {t("betaBadge")}
            </Badge>
          </CardTitle>
          <CardDescription>{t("description")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-start justify-between gap-4 rounded-md border p-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Lock className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">{t("httpsLabel")}</span>
                {httpsEnabled && certPresent && (
                  <Badge variant="default" className="text-[10px] bg-board-green">
                    <ShieldCheck className="h-3 w-3 mr-1" />
                    {t("httpsActive")}
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground">{t("httpsDescription")}</p>
              <p className="text-xs text-muted-foreground flex items-start gap-1.5 pt-1">
                <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                <span>{t("httpsWarning")}</span>
              </p>
            </div>
            <Switch
              checked={httpsEnabled}
              disabled={mutation.isPending}
              onCheckedChange={(checked) => mutation.mutate(checked)}
              aria-label={t("httpsLabel")}
            />
          </div>
        </CardContent>
      </Card>

      <Dialog open={restartPrompt !== null} onOpenChange={(open) => !open && !restarting && setRestartPrompt(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {restartPrompt === "enabled" ? t("restartDialogTitleEnabled") : t("restartDialogTitleDisabled")}
            </DialogTitle>
            <DialogDescription>
              {restartPrompt === "enabled"
                ? t("restartDialogDescriptionEnabled")
                : t("restartDialogDescriptionDisabled")}
              {!updaterAvailable && (
                <>
                  <br />
                  <br />
                  <span className="text-muted-foreground">{t("restartManualHint")}</span>
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRestartPrompt(null)} disabled={restarting}>
              {tCommon("cancel")}
            </Button>
            {updaterAvailable && (
              <Button onClick={() => restartMutation.mutate()} disabled={restarting || restartMutation.isPending}>
                {restarting || restartMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4 mr-2" />
                )}
                {t("restartNow")}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
