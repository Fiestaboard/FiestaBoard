"use client";

import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Flex,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { api, AUTO_UPDATE_INTERVALS, type AutoUpdateInterval } from "@/lib/api";

/**
 * Settings → System → "Check for updates" interval card.
 *
 * Lets the user pick how often FiestaBoard should automatically check for
 * a newer container image: Daily, Weekly (default), Monthly, or Manual.
 *
 * The actual check loop runs in the API process (see
 * ``_system_update_check_loop`` in ``src/api_server.py``); this card just
 * persists the user's choice and shows when the last check happened so
 * users have confidence the schedule is doing its job.
 */
const INTERVAL_LABELS: Record<AutoUpdateInterval, string> = {
  daily: "Every day",
  weekly: "Every week",
  monthly: "Every month",
  manual: "Manual only",
};

const INTERVAL_DESCRIPTIONS: Record<AutoUpdateInterval, string> = {
  daily: "Check for new releases once a day. Best if you want updates as soon as they ship.",
  weekly: "Check once a week. A good balance of staying current without nagging.",
  monthly: "Check once a month. Quietest option that still alerts you periodically.",
  manual: "No background checks. Use the refresh button on this page to check on demand.",
};

function formatLastCheck(iso: string | null | undefined): string {
  if (!iso) return "Never";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "Never";
    return d.toLocaleString();
  } catch {
    return "Never";
  }
}

export function AutoUpdateIntervalCard() {
  const t = useTranslations("systemUpdate");
  const queryClient = useQueryClient();

  const { data: status, isLoading } = useQuery({
    queryKey: ["update-status"],
    queryFn: () => api.getUpdateStatus(),
    staleTime: 1000 * 30,
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: (interval: AutoUpdateInterval) => api.setAutoUpdateInterval(interval),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["update-status"] });
    },
  });

  // Manual "Check now" — bypasses the background scheduler so users can pull
  // a fresh check the moment they hear about a new release. Auto-install
  // behavior is unaffected; this only triggers the check.
  const checkNowMutation = useMutation({
    mutationFn: () => api.checkForUpdate(),
    onSuccess: (result) => {
      // Refresh both queries so the SystemUpdate banner and "Last checked"
      // timestamp update immediately.
      queryClient.setQueryData(["update-check"], result);
      queryClient.invalidateQueries({ queryKey: ["update-check"] });
      queryClient.invalidateQueries({ queryKey: ["update-status"] });

      if (result.error) {
        toast.error(t("checkFailedToast", { error: result.error }));
      } else if (result.update_available && result.latest_version) {
        toast.info(t("updateAvailableToast", { version: result.latest_version }));
      } else {
        toast.success(t("upToDateToast", { version: result.current_version ?? "" }));
      }
    },
    onError: (err: Error) => {
      toast.error(t("checkFailedToast", { error: err.message }));
    },
  });

  // Hide the card entirely when the status query failed — the rest of the
  // System page already surfaces that error, and a half-broken selector is
  // worse than nothing.
  if (isLoading || !status) {
    return null;
  }

  const current: AutoUpdateInterval = status.auto_update_interval ?? "weekly";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <CalendarClock className="h-4 w-4" />
          {t("checkForUpdates")}
        </CardTitle>
        <CardDescription>
          How often FiestaBoard should look for a new release in the background. You&apos;ll see a banner here when one
          is found.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Flex wrap align="center" gap="3">
          <Select
            value={current}
            onValueChange={(v) => mutation.mutate(v as AutoUpdateInterval)}
            disabled={mutation.isPending}
          >
            <SelectTrigger className="w-[180px]" aria-label="Update check frequency">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {AUTO_UPDATE_INTERVALS.map((key) => (
                <SelectItem key={key} value={key}>
                  {INTERVAL_LABELS[key]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Text as="span" size="xs" tone="muted">
            Last checked: {formatLastCheck(status.last_check)}
          </Text>
          <Button
            variant="outline"
            size="sm"
            onClick={() => checkNowMutation.mutate()}
            disabled={checkNowMutation.isPending}
            className="ml-auto"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${checkNowMutation.isPending ? "animate-spin" : ""}`} />
            {checkNowMutation.isPending ? t("checkingForUpdates") : t("checkNow")}
          </Button>
        </Flex>
        <Text tone="muted">{INTERVAL_DESCRIPTIONS[current]}</Text>
      </CardContent>
    </Card>
  );
}
