"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Timer } from "lucide-react";
import { useDeferredValue, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

export function UpdateIntervals() {
  const t = useTranslations("generalSettings");
  const tc = useTranslations("common");
  const queryClient = useQueryClient();

  const [pollingInterval, setPollingInterval] = useState(15);
  const [boardReadIntervalLocal, setBoardReadIntervalLocal] = useState(30);
  const [boardReadIntervalCloud, setBoardReadIntervalCloud] = useState(180);

  const { data: allSettings, isLoading } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const deferredPolling = useDeferredValue(allSettings?.polling);
  const initializedRef = useRef(false);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (deferredPolling && !initializedRef.current) {
      setPollingInterval(deferredPolling.interval_seconds);
      setBoardReadIntervalLocal(deferredPolling.board_read_interval_local ?? 30);
      setBoardReadIntervalCloud(deferredPolling.board_read_interval_cloud ?? 180);
      initializedRef.current = true;
      setInitialized(true);
    }
  }, [deferredPolling]);

  const updatePollingMutation = useMutation({
    mutationFn: (updates: Parameters<typeof api.updatePollingSettings>[0]) => api.updatePollingSettings(updates),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["polling-settings"] });
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
      if (data.requires_restart) {
        toast.success(t("toastPollingUpdatedRestart"), { duration: 5000 });
      } else {
        toast.success(t("toastPollingUpdated"));
      }
    },
    onError: (error: Error) => {
      toast.error(t("toastPollingFailed", { error: error.message }));
    },
  });

  const updateBoardReadIntervalMutation = useMutation({
    mutationFn: (updates: Parameters<typeof api.updatePollingSettings>[0]) => api.updatePollingSettings(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["polling-settings"] });
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
      toast.success(t("toastBoardReadIntervalUpdated"));
    },
    onError: (error: Error) => {
      toast.error(t("toastBoardReadIntervalFailed", { error: error.message }));
    },
  });

  const isSaving = updatePollingMutation.isPending || updateBoardReadIntervalMutation.isPending;

  const handlePollingIntervalChange = (value: string) => {
    const interval = parseInt(value, 10);
    if (!isNaN(interval) && interval >= 10) {
      setPollingInterval(interval);
    }
  };

  const handlePollingIntervalBlur = () => {
    updatePollingMutation.mutate({ interval_seconds: pollingInterval });
  };

  const handleBoardReadIntervalLocalBlur = () => {
    const clamped = Math.max(20, boardReadIntervalLocal);
    setBoardReadIntervalLocal(clamped);
    updateBoardReadIntervalMutation.mutate({ board_read_interval_local: clamped });
  };

  const handleBoardReadIntervalCloudBlur = () => {
    const clamped = Math.max(20, boardReadIntervalCloud);
    setBoardReadIntervalCloud(clamped);
    updateBoardReadIntervalMutation.mutate({ board_read_interval_cloud: clamped });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Timer className="h-4 w-4" />
          {t("updateIntervalsTitle")}
        </CardTitle>
        <CardDescription>{t("updateIntervalsDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {isLoading || !initialized ? (
          <div className="space-y-6">
            <div className="space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-10 w-32" />
              <Skeleton className="h-3 w-40" />
            </div>
            <div className="space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-10 w-32" />
            </div>
            <div className="space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-10 w-32" />
            </div>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              <Label htmlFor="polling-interval" className="text-sm font-medium">
                {t("boardUpdateIntervalLabel")}
              </Label>
              <p className="text-xs text-muted-foreground">{t("boardUpdateIntervalDescription")}</p>
              <div className="flex items-center gap-3">
                <Input
                  id="polling-interval"
                  type="number"
                  min={10}
                  max={3600}
                  value={pollingInterval}
                  onChange={(e) => handlePollingIntervalChange(e.target.value)}
                  onBlur={handlePollingIntervalBlur}
                  disabled={isSaving}
                  className="w-32"
                />
                <span className="text-sm text-muted-foreground">{tc("seconds")}</span>
              </div>
              <p className="text-xs text-muted-foreground">{t("requiresServiceRestart")}</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="board-read-local" className="text-sm font-medium">
                {t("boardReadIntervalLocalLabel")}
              </Label>
              <p className="text-xs text-muted-foreground">{t("boardReadIntervalLocalDescription")}</p>
              <div className="flex items-center gap-3">
                <Input
                  id="board-read-local"
                  type="number"
                  min={20}
                  max={3600}
                  value={boardReadIntervalLocal}
                  onChange={(e) => {
                    const v = parseInt(e.target.value, 10);
                    if (!isNaN(v)) setBoardReadIntervalLocal(v);
                  }}
                  onBlur={handleBoardReadIntervalLocalBlur}
                  disabled={updateBoardReadIntervalMutation.isPending}
                  className="w-32"
                />
                <span className="text-sm text-muted-foreground">{tc("seconds")}</span>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="board-read-cloud" className="text-sm font-medium">
                {t("boardReadIntervalCloudLabel")}
              </Label>
              <p className="text-xs text-muted-foreground">{t("boardReadIntervalCloudDescription")}</p>
              <div className="flex items-center gap-3">
                <Input
                  id="board-read-cloud"
                  type="number"
                  min={20}
                  max={3600}
                  value={boardReadIntervalCloud}
                  onChange={(e) => {
                    const v = parseInt(e.target.value, 10);
                    if (!isNaN(v)) setBoardReadIntervalCloud(v);
                  }}
                  onBlur={handleBoardReadIntervalCloudBlur}
                  disabled={updateBoardReadIntervalMutation.isPending}
                  className="w-32"
                />
                <span className="text-sm text-muted-foreground">{tc("seconds")}</span>
              </div>
              {boardReadIntervalCloud < 60 && <p className="text-xs text-warning">{t("boardReadIntervalWarning")}</p>}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
