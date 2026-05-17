"use client";

import { useState, useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { Timer } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { Page, SetTemporaryOverrideRequest } from "@/lib/api";

const DURATION_PRESETS = [
  { label: "5 min", minutes: 5 },
  { label: "15 min", minutes: 15 },
  { label: "30 min", minutes: 30 },
  { label: "1 hr", minutes: 60 },
] as const;

type RevertMode = "schedule" | "blank" | "page";

interface ForceSetDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pageId: string | null;
  pageName: string;
  scheduleEnabled: boolean;
  pages: Page[];
}

export function ForceSetDialog({
  open,
  onOpenChange,
  pageId,
  pageName,
  scheduleEnabled,
  pages,
}: ForceSetDialogProps) {
  const t = useTranslations("forceSetDialog");
  const queryClient = useQueryClient();

  const [durationMinutes, setDurationMinutes] = useState<number>(5);
  const [customMinutes, setCustomMinutes] = useState<string>("");
  const [isCustom, setIsCustom] = useState(false);
  const [revertMode, setRevertMode] = useState<RevertMode>(
    scheduleEnabled ? "schedule" : "blank"
  );
  const [revertPageId, setRevertPageId] = useState<string>("");

  const effectiveDuration = isCustom
    ? Math.max(1, Math.min(480, parseInt(customMinutes, 10) || 1))
    : durationMinutes;

  const setOverrideMutation = useMutation({
    mutationFn: (req: SetTemporaryOverrideRequest) =>
      api.setTemporaryOverride(req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"] });
      queryClient.invalidateQueries({ queryKey: ["temporaryOverride"] });
      // Clear display cache so board shows override page on next poll
      api.forceRefresh().catch(() => {});
      const mins = effectiveDuration;
      toast.success(
        t("toastSuccess", { minutes: mins, pageName })
      );
      onOpenChange(false);
    },
    onError: (err: Error) => {
      toast.error(err.message || t("toastError"));
    },
  });

  const handleConfirm = useCallback(() => {
    if (!pageId) return;
    const req: SetTemporaryOverrideRequest = {
      page_id: pageId,
      duration_minutes: effectiveDuration,
      revert_mode: revertMode,
      revert_page_id: revertMode === "page" ? revertPageId || undefined : undefined,
    };
    setOverrideMutation.mutate(req);
  }, [pageId, effectiveDuration, revertMode, revertPageId, setOverrideMutation]);

  const isValid =
    pageId !== null &&
    effectiveDuration >= 1 &&
    effectiveDuration <= 480 &&
    (!isCustom || (customMinutes !== "" && !isNaN(parseInt(customMinutes, 10)))) &&
    (revertMode !== "page" || revertPageId !== "");

  const otherPages = pages.filter((p) => p.id !== pageId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Timer className="h-5 w-5" />
            {t("title")}
          </DialogTitle>
          <DialogDescription>
            {t("description", { pageName })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          {/* Duration selection */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">{t("showFor")}</Label>
            <div className="flex flex-wrap gap-2">
              {DURATION_PRESETS.map((preset) => (
                <button
                  key={preset.minutes}
                  type="button"
                  onClick={() => {
                    setDurationMinutes(preset.minutes);
                    setIsCustom(false);
                  }}
                  className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                    !isCustom && durationMinutes === preset.minutes
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input bg-background hover:bg-accent hover:text-accent-foreground"
                  }`}
                >
                  {preset.label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setIsCustom(true)}
                className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  isCustom
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input bg-background hover:bg-accent hover:text-accent-foreground"
                }`}
              >
                {t("custom")}
              </button>
            </div>
            {isCustom && (
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={1}
                  max={480}
                  value={customMinutes}
                  onChange={(e) => setCustomMinutes(e.target.value)}
                  placeholder="1–480"
                  className="w-24"
                  autoFocus
                />
                <span className="text-sm text-muted-foreground">
                  {t("minutes")}
                </span>
              </div>
            )}
          </div>

          {/* Revert mode */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">{t("afterTimer")}</Label>
            <div className="space-y-2">
              {scheduleEnabled && (
                <label className="flex cursor-pointer items-center gap-2.5">
                  <input
                    type="radio"
                    name="revert"
                    value="schedule"
                    checked={revertMode === "schedule"}
                    onChange={() => setRevertMode("schedule")}
                    className="h-4 w-4 accent-primary"
                  />
                  <span className="text-sm">{t("revertSchedule")}</span>
                </label>
              )}
              <label className="flex cursor-pointer items-center gap-2.5">
                <input
                  type="radio"
                  name="revert"
                  value="blank"
                  checked={revertMode === "blank"}
                  onChange={() => setRevertMode("blank")}
                  className="h-4 w-4 accent-primary"
                />
                <span className="text-sm">{t("revertBlank")}</span>
              </label>
              <label className="flex cursor-pointer items-center gap-2.5">
                <input
                  type="radio"
                  name="revert"
                  value="page"
                  checked={revertMode === "page"}
                  onChange={() => setRevertMode("page")}
                  className="h-4 w-4 accent-primary"
                />
                <span className="text-sm">{t("revertPage")}</span>
              </label>
              {revertMode === "page" && (
                <div className="ml-6">
                  <select
                    value={revertPageId}
                    onChange={(e) => setRevertPageId(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <option value="">{t("selectPage")}</option>
                    {otherPages.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={setOverrideMutation.isPending}
          >
            {t("cancel")}
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!isValid || setOverrideMutation.isPending}
          >
            <Timer className="mr-1.5 h-4 w-4" />
            {setOverrideMutation.isPending ? t("setting") : t("confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
