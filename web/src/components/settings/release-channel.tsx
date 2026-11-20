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
  Flex,
  StatusDot,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeInfo } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { SettingsPanel } from "@/components/settings/settings-panel";
import { useUpdate } from "@/components/update-context";
import { useAvailableUpdate } from "@/hooks/use-available-update";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api } from "@/lib/api";
import type { ReleaseChannel } from "@/lib/api/system";

const CHANNELS: ReleaseChannel[] = ["stable", "beta", "alpha"];
const LABELS = { stable: "channelStable", beta: "channelBeta", alpha: "channelAlpha" } as const;

/**
 * Settings › System & backups › Version (07e `320:8881`): the running version
 * and whether it is current, then the release channel. Exploring channels
 * never installs an image.
 */
export function ReleaseChannelCard() {
  const t = useTranslations("releaseChannel");
  const queryClient = useQueryClient();
  const { startUpdate } = useUpdate();
  const updateVersion = useAvailableUpdate();
  // Shared cache keys with SystemControls / useAvailableUpdate.
  const { data: updateStatus } = useQuery({
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
  const runningVersion = t("runningVersion", { version: data.running_version });
  // Say "Up to date" (green) only when the check says so; while it loads,
  // when it failed, or when Home Assistant owns updates, claim nothing.
  const upToDate =
    !updateStatus?.managed_externally && !!updateCheck && !updateCheck.error && !updateCheck.update_available;
  const versionLine = updateVersion
    ? `${runningVersion} · ${t("updateAvailable", { version: updateVersion })}`
    : upToDate
      ? `${runningVersion} · ${t("upToDate")}`
      : runningVersion;
  const versionStatus = updateVersion ? "warning" : upToDate ? "success" : "neutral";
  // The running channel's version is known here; the others are discovered.
  const versionOf = (channel: ReleaseChannel) =>
    channel === current && data.running_version
      ? data.running_version
      : versions.isPending
        ? t("versionLoading")
        : (versions.data?.channel_versions[channel] ?? t("versionUnavailable"));

  return (
    <SettingsPanel icon={<BadgeInfo />} title={t("versionTitle")} {...anchorProps("settings.release_channel")}>
      <Flex align="center" gap="2">
        <StatusDot status={versionStatus} />
        <Text size="sm">{versionLine}</Text>
      </Flex>
      <Text size="sm" weight="medium" className="mt-3">
        {t("title")}
      </Text>
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
                // Not `meta`: the kit draws meta as an uppercase mono code, and
                // a version is a number to read as written.
                description={
                  <>
                    <Text as="span" className="block">
                      {t(`${channel}Description`)}
                    </Text>
                    <Text as="span" size="sm" tone="muted" className="block">
                      {versionOf(channel)}
                    </Text>
                  </>
                }
              />
            ))}
          </ChoiceCardGroup>
          <Text size="xs" tone="muted">
            {t("chooserDescription")}
          </Text>
          <Button disabled={selected === current || switchMutation.isPending} onClick={() => setTarget(selected)}>
            {t("switchCta")}
          </Button>
        </>
      ) : (
        // The server's reason is written for whoever runs the hub (compose
        // profiles, sidecars) — never shown here (BB-C-13).
        <Text size="sm" tone="muted">
          {updateStatus?.managed_externally ? t("managedExternally") : t("switchUnavailable")}
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
