"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Button,
  Flex,
  PageSection,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FlaskConical } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useUpdate } from "@/components/update-context";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

/**
 * Settings → System → "Release channel".
 *
 * Opting INTO the beta lives here, on the stable build, because that is the
 * only place it can be discovered: a control that shipped only on the beta
 * could only be found by someone who had already opted in. Opting back out
 * lives on the beta build, which is where you are by then.
 *
 * Renders nothing when switching is unavailable and there is nothing useful
 * to say about it — Home Assistant installs, where the Supervisor owns
 * updating, get an explanation instead of a dead button.
 */
export function ReleaseChannelCard() {
  const t = useTranslations("releaseChannel");
  const queryClient = useQueryClient();
  const { startUpdate } = useUpdate();
  const [confirming, setConfirming] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["system", "channel"],
    queryFn: () => api.getReleaseChannel(),
    staleTime: 60_000,
  });

  const switchMutation = useMutation({
    mutationFn: (channel: "stable" | "beta") => api.setReleaseChannel(channel),
    onSuccess: () => {
      setConfirming(false);
      queryClient.invalidateQueries({ queryKey: ["system", "channel"] });
      // The container is about to be recreated. Hand off to the same
      // overlay the Update Now button uses so the reconnect is handled
      // identically rather than reinvented here. No version argument: the
      // overlay's /version-difference check is only a fallback, and the
      // number we are moving to is not known until the new image boots.
      startUpdate();
    },
    onError: (error: Error) => {
      setConfirming(false);
      toast.error(t("switchFailedToast", { error: error.message }));
    },
  });

  if (isLoading || !data) return null;

  const onBeta = data.channel === "beta";

  return (
    <PageSection title={t("title")} description={t("description")}>
      <Flex align="start" justify="between" gap="4" className="rounded-md border p-4">
        <Flex direction="col" gap="1" className="min-w-0">
          <Flex align="center" gap="2">
            <FlaskConical className="h-4 w-4 shrink-0" aria-hidden="true" />
            <Text weight="medium">{t("currentLabel")}</Text>
            <Badge variant={onBeta ? "default" : "secondary"}>{onBeta ? t("channelBeta") : t("channelStable")}</Badge>
          </Flex>

          {onBeta ? (
            <Text size="sm" variant="muted">
              {t("onBetaBody")}
            </Text>
          ) : (
            <Text size="sm" variant="muted">
              {t("onStableBody")}
            </Text>
          )}

          {!data.can_switch && data.reason && (
            <Flex align="start" gap="2" className="mt-1">
              <AlertTriangle className="text-warning mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <Text size="sm" variant="muted">
                {data.reason}
              </Text>
            </Flex>
          )}
        </Flex>

        {data.can_switch && !onBeta && (
          <Button variant="outline" onClick={() => setConfirming(true)} disabled={switchMutation.isPending}>
            {t("joinCta")}
          </Button>
        )}
      </Flex>

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              <Flex align="center" gap="2">
                <AlertTriangle className="text-warning h-5 w-5" aria-hidden="true" />
                {t("confirmTitle")}
              </Flex>
            </AlertDialogTitle>
            {/* The data warning is the whole point of the confirm step. A
                beta can migrate settings and pages to a schema the stable
                build refuses to read, so the snapshot taken on the way in
                is the way back. Say that before the switch, not after. */}
            <AlertDialogDescription>{t("confirmBody")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={switchMutation.isPending}>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => switchMutation.mutate("beta")} disabled={switchMutation.isPending}>
              {switchMutation.isPending ? t("switching") : t("confirmCta")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageSection>
  );
}
