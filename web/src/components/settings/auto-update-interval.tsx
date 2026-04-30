"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AutoUpdateInterval, AUTO_UPDATE_INTERVALS } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CalendarClock } from "lucide-react";

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
  const queryClient = useQueryClient();

  const { data: status, isLoading } = useQuery({
    queryKey: ["update-status"],
    queryFn: () => api.getUpdateStatus(),
    staleTime: 1000 * 30,
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: (interval: AutoUpdateInterval) =>
      api.setAutoUpdateInterval(interval),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["update-status"] });
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
          Check for updates
        </CardTitle>
        <CardDescription>
          How often FiestaBoard should look for a new release in the
          background. You&apos;ll see a banner here when one is found.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <Select
            value={current}
            onValueChange={(v) =>
              mutation.mutate(v as AutoUpdateInterval)
            }
            disabled={mutation.isPending}
          >
            <SelectTrigger
              className="w-[180px]"
              aria-label="Update check frequency"
            >
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
          <span className="text-xs text-muted-foreground">
            Last checked: {formatLastCheck(status.last_check)}
          </span>
        </div>
        <p className="text-sm text-muted-foreground">
          {INTERVAL_DESCRIPTIONS[current]}
        </p>
      </CardContent>
    </Card>
  );
}
