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
  ChoiceCard,
  ChoiceCardGroup,
  PageSection,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useUpdate } from "@/components/update-context";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api } from "@/lib/api";
import type { ReleaseChannel } from "@/lib/api/system";

const CHANNELS: ReleaseChannel[] = ["stable", "beta", "alpha"];
const LABELS = { stable: "channelStable", beta: "channelBeta", alpha: "channelAlpha" } as const;

/** Settings → System; the current selection always describes the running image. */
export function ReleaseChannelCard() {
  const t = useTranslations("releaseChannel");
  const queryClient = useQueryClient();
  const { startUpdate } = useUpdate();
  const [target, setTarget] = useState<ReleaseChannel | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["system", "channel"],
    queryFn: () => api.getReleaseChannel(),
    staleTime: 60_000,
  });
  const switchMutation = useMutation({
    // A separate dialog action explicitly confirms the major-upgrade warning.
    mutationFn: (channel: ReleaseChannel) => api.setReleaseChannel(channel, true),
    onSuccess: (result) => {
      setTarget(null);
      if (result?.warning) toast.warning(result.warning);
      queryClient.invalidateQueries({ queryKey: ["system", "channel"] });
      startUpdate();
    },
    onError: (error: Error) => {
      setTarget(null);
      toast.error(t("switchFailedToast", { error: error.message }));
    },
  });
  if (isLoading || !data) return null;
  const current = data.running_channel ?? data.channel;
  const leaving = (current === "alpha" && target !== "alpha") || (current === "beta" && target === "stable");

  return (
    <PageSection
      icon={<FlaskConical />}
      title={t("title")}
      description={t("chooserDescription")}
      {...anchorProps("settings.release_channel")}
    >
      {data.can_switch ? (
        <ChoiceCardGroup
          aria-label={t("title")}
          value={current}
          disabled={switchMutation.isPending}
          onValueChange={(value) => {
            if (CHANNELS.includes(value as ReleaseChannel) && value !== current) setTarget(value as ReleaseChannel);
          }}
          {...anchorProps("settings.release_channel.channel")}
        >
          {CHANNELS.map((channel) => (
            <ChoiceCard
              key={channel}
              value={channel}
              disabled={!data.available_channels.includes(channel)}
              title={
                <>
                  {t(LABELS[channel])} {current === channel && <Badge variant="secondary">{t("currentBadge")}</Badge>}
                </>
              }
              description={t(`${channel}Description`)}
              meta={data.channel_versions?.[channel] ?? t("versionUnavailable")}
            />
          ))}
        </ChoiceCardGroup>
      ) : (
        <Text size="sm" tone="muted">
          {data.reason ?? t("switchUnavailable")}
        </Text>
      )}
      <AlertDialog
        open={target !== null}
        onOpenChange={(open) => {
          if (!open && !switchMutation.isPending) setTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("switchTitle", { channel: target ? t(LABELS[target]) : "" })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t(target === "alpha" ? "alphaConfirmBody" : leaving ? "downgradeConfirmBody" : "betaConfirmBody")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={switchMutation.isPending}>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              disabled={switchMutation.isPending}
              onClick={() => {
                if (target) switchMutation.mutate(target);
              }}
            >
              {switchMutation.isPending ? t("switching") : t("switchCta")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageSection>
  );
}
