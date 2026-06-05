"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Timer } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SetTemporaryOverrideRequest } from "@/lib/api";
import { api } from "@/lib/api";

const DURATION_PRESETS = [
  { label: "5 min", minutes: 5 },
  { label: "15 min", minutes: 15 },
  { label: "30 min", minutes: 30 },
  { label: "1 hr", minutes: 60 },
] as const;

interface ForceSetDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pageId: string | null;
  pageName: string;
}

export function ForceSetDialog({ open, onOpenChange, pageId, pageName }: ForceSetDialogProps) {
  const t = useTranslations("forceSetDialog");
  const queryClient = useQueryClient();

  const [durationMinutes, setDurationMinutes] = useState<number>(5);
  const [customMinutes, setCustomMinutes] = useState<string>("");
  const [isCustom, setIsCustom] = useState(false);

  useEffect(() => {
    if (open) {
      setDurationMinutes(5);
      setCustomMinutes("");
      setIsCustom(false);
    }
  }, [open]);

  const effectiveDuration = isCustom ? Math.max(1, Math.min(480, parseInt(customMinutes, 10) || 1)) : durationMinutes;

  const setOverrideMutation = useMutation({
    mutationFn: (req: SetTemporaryOverrideRequest) => api.setTemporaryOverride(req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"] });
      queryClient.invalidateQueries({ queryKey: ["temporaryOverride"] });
      api.forceRefresh().catch(() => {});
      toast.success(t("toastSuccess", { minutes: effectiveDuration, pageName }));
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
      revert_mode: "schedule",
    };
    setOverrideMutation.mutate(req);
  }, [pageId, effectiveDuration, setOverrideMutation]);

  const isValid =
    pageId !== null &&
    effectiveDuration >= 1 &&
    effectiveDuration <= 480 &&
    (!isCustom || (customMinutes !== "" && !isNaN(parseInt(customMinutes, 10))));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Timer className="h-5 w-5" />
            {t("title")}
          </DialogTitle>
          <DialogDescription>{t("description", { pageName })}</DialogDescription>
        </DialogHeader>

        <div className="py-2">
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
                <span className="text-sm text-muted-foreground">{t("minutes")}</span>
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={setOverrideMutation.isPending}>
            {t("cancel")}
          </Button>
          <Button onClick={handleConfirm} disabled={!isValid || setOverrideMutation.isPending}>
            <Timer className="mr-1.5 h-4 w-4" />
            {setOverrideMutation.isPending ? t("setting") : t("confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
