"use client";

import {
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Input,
  Label,
  SegmentedControl,
  SegmentedControlItem,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Timer } from "lucide-react";
import { useCallback, useId, useState } from "react";
import { toast } from "sonner";

import { SilenceNotice } from "@/components/silence-notice";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useTranslations } from "@/i18n/translations";
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
  /**
   * When the PRIMARY board's silence ends ("7:00 AM") — the override store is
   * primary-only, so that is the board Force Set wakes (#1943, #949). Set
   * (with `silenced`) only while that board is silenced.
   */
  silencedUntil?: string | null;
  /** The primary board is silenced. Defaults to "`silencedUntil` is set". */
  silenced?: boolean;
}

export function ForceSetDialog({
  open,
  onOpenChange,
  pageId,
  pageName,
  silencedUntil = null,
  silenced = silencedUntil != null,
}: ForceSetDialogProps) {
  const t = useTranslations("forceSetDialog");
  const queryClient = useQueryClient();

  const [durationMinutes, setDurationMinutes] = useState<number>(5);
  const [customMinutes, setCustomMinutes] = useState<string>("");
  const [isCustom, setIsCustom] = useState(false);
  const showForId = useId();

  // Reset the duration picker each time the dialog opens. Done during render
  // so the dialog's first painted frame already shows the defaults instead of
  // last time's selection (react-hooks/set-state-in-effect, issue #1568).
  if (useDepsChanged([open]) && open) {
    setDurationMinutes(5);
    setCustomMinutes("");
    setIsCustom(false);
  }

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

        {/* Force Set deliberately beats silence (#949). Say so before the
            click, and name the choice on the button. */}
        <SilenceNotice
          active={silenced}
          variant="warning"
          until={silencedUntil}
          description={t("silenceWarning")}
          data-testid="force-set-silence"
        />

        <Box className="py-2">
          <Stack gap="2">
            <Label id={showForId} className="text-sm font-medium">
              {t("showFor")}
            </Label>
            <SegmentedControl
              aria-labelledby={showForId}
              value={isCustom ? "custom" : String(durationMinutes)}
              onValueChange={(value) => {
                if (value === "custom") {
                  setIsCustom(true);
                  return;
                }
                setDurationMinutes(Number(value));
                setIsCustom(false);
              }}
            >
              {DURATION_PRESETS.map((preset) => (
                <SegmentedControlItem key={preset.minutes} value={String(preset.minutes)}>
                  {preset.label}
                </SegmentedControlItem>
              ))}
              <SegmentedControlItem value="custom">{t("custom")}</SegmentedControlItem>
            </SegmentedControl>
            {isCustom && (
              <Flex align="center" gap="2">
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
                <Text as="span" size="sm" tone="muted">
                  {t("minutes")}
                </Text>
              </Flex>
            )}
          </Stack>
        </Box>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={setOverrideMutation.isPending}>
            {t("cancel")}
          </Button>
          <Button onClick={handleConfirm} disabled={!isValid || setOverrideMutation.isPending}>
            <Timer className="mr-1.5 h-4 w-4" />
            {setOverrideMutation.isPending ? t("setting") : silenced ? t("confirmSilenced") : t("confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
