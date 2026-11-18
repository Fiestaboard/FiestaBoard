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
  ChoiceCard,
  ChoiceCardGroup,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { SettingsPanel } from "@/components/settings/settings-panel";
import { useUpdate } from "@/components/update-context";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api } from "@/lib/api";
import type { ReleaseChannel } from "@/lib/api/system";

const CHANNELS: ReleaseChannel[] = ["stable", "beta", "alpha"];
const LABELS = { stable: "channelStable", beta: "channelBeta", alpha: "channelAlpha" } as const;

/** Settings → System; exploring channels never installs an image. */
export function ReleaseChannelCard() {
  const t = useTranslations("releaseChannel");
  const queryClient = useQueryClient();
  const { startUpdate } = useUpdate();
  const [selection, setSelection] = useState<ReleaseChannel | null>(null);
  const [target, setTarget] = useState<ReleaseChannel | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["system", "channel"],
    queryFn: () => api.getReleaseChannel(),
    staleTime: 60_000,
  });
  const versions = useQuery({
    queryKey: ["system", "channel", "versions"],
    queryFn: () => api.getReleaseChannelVersions(),
    enabled: !!data?.can_switch,
    staleTime: 60_000,
    retry: false,
  });
  const switchMutation = useMutation({
    // A separate dialog action explicitly confirms the major-upgrade warning.
    mutationFn: (channel: ReleaseChannel) => {
      const targetVersion = versions.data?.channel_versions[channel];
      const targetMajor = targetVersion ? Number.parseInt(targetVersion, 10) : channel === "alpha" ? 11 : NaN;
      const runningMajor = Number.parseInt(data?.running_version ?? "", 10);
      return api.setReleaseChannel(channel, targetMajor > runningMajor);
    },
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
  const selected = selection ?? current;
  const leaving = (current === "alpha" && target !== "alpha") || (current === "beta" && target === "stable");

  return (
    <SettingsPanel
      icon={<FlaskConical />}
      title={t("title")}
      description={t("chooserDescription")}
      {...anchorProps("settings.release_channel")}
    >
      {data.can_switch ? (
        <>
          <ChoiceCardGroup
            aria-label={t("title")}
            value={selected}
            disabled={switchMutation.isPending}
            onValueChange={(value) => {
              if (CHANNELS.includes(value as ReleaseChannel)) setSelection(value as ReleaseChannel);
            }}
            onKeyDown={(event) => {
              if ((event.key === "Enter" || event.key === " ") && selected !== current) {
                event.preventDefault();
                setTarget(selected);
              }
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
                meta={
                  versions.isPending
                    ? t("versionLoading")
                    : (versions.data?.channel_versions[channel] ?? t("versionUnavailable"))
                }
              />
            ))}
          </ChoiceCardGroup>
          <Button disabled={selected === current || switchMutation.isPending} onClick={() => setTarget(selected)}>
            {t("switchCta")}
          </Button>
        </>
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
    </SettingsPanel>
  );
}
