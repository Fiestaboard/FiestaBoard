"use client";

import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Code,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  PageSection,
  Text,
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

  // Under an external supervisor (the Home Assistant add-on) updates flow
  // through the Supervisor's add-on store, not this banner. Suppress the whole
  // alert — including the docker-compose "enable one-click updates" hint,
  // which is meaningless in an add-on install with no compose file.
  if (status?.managed_externally) {
    return null;
  }

  const sidecarReady = !!status?.updater_available;

  return (
    // The section belongs to the banner, not to the route. Every `return
    // null` above is a case where the settings card must show no block at
    // all, and a `PageSection` wrapped around this component in settings.tsx
    // could not honour that — it pads itself 24px top and bottom and draws a
    // divider whether or not its child renders anything, so an install with
    // no update pending (the usual case) got an empty band under the page
    // header. Only this component can know; the answer is in its own query.
    <PageSection>
      <TooltipProvider>
        {/* `variant="warning"` rather than the `default` variant tinted with raw
            `border-warning/50 bg-warning/10` classes: @fiestaboard/ui 6 owns the
            warning recipe (border, 8% fill, and `[&>svg]:text-warning` on the
            icon) and derives the announcement role from the variant, so the
            hand-rolled version rendered `role="status"` and stopped announcing. */}
        <Alert variant="warning">
          <ArrowUpCircle className="h-4 w-4" />
          <AlertDescription className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <Flex align="center" gap="2" wrap>
              <Text as="span" weight="medium">
                {t("updateAvailable")}
              </Text>
              <Badge variant="secondary" className="text-xs">
                {tCommon("versionShort", { version: updateCheck.latest_version })}
              </Badge>
              <Text as="span" tone="muted">
                {t("youAreRunning", { currentVersion: updateCheck.current_version })}
              </Text>
            </Flex>
            <Flex align="center" gap="2">
              <Button variant="outline" size="sm" asChild>
                {/* Plain <a> stays raw: it is the single Slot child of Button asChild,
                  which merges button styling onto it; TextLink would layer conflicting
                  link/underline treatment on top. */}
                {/* eslint-disable-next-line react/forbid-elements -- single Slot child of Button asChild; the Button merges its chrome onto this anchor and TextLink would layer conflicting link styling */}
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
                  <Text>{t("checkForUpdates")}</Text>
                </TooltipContent>
              </Tooltip>
            </Flex>
          </AlertDescription>
        </Alert>

        {!sidecarReady && (
          <Text size="xs" tone="muted" className="mt-2 ml-1">
            {t.rich("oneClickHint", {
              profile: () => <Code>COMPOSE_PROFILES=fiestaupdater</Code>,
              envFile: () => <Code>.env</Code>,
              command: () => <Code>docker compose up -d</Code>,
            })}
          </Text>
        )}

        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("dialogTitle")}</DialogTitle>
              <DialogDescription>
                {t.rich("dialogDescription", {
                  version: () => (
                    <Text as="span" weight="semibold" tone="muted">
                      {tCommon("versionShort", { version: updateCheck.latest_version })}
                    </Text>
                  ),
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
    </PageSection>
  );
}
