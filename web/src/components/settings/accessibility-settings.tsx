"use client";

import { Box, Flex, Skeleton, Switch, Text } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Accessibility } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { SettingsPanel } from "@/components/settings/settings-panel";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

export function AccessibilitySettings() {
  const t = useTranslations("profile");
  const tPanels = useTranslations("settings.panels");
  const queryClient = useQueryClient();

  const [reduceMotion, setReduceMotion] = useState(false);

  const { data: allSettings, isLoading } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  // Mirror the server value into the switch during render, not in an effect:
  // an effect would commit the default `false` first and flip the switch in a
  // second render (react-hooks/set-state-in-effect, issue #1568).
  const display = allSettings?.display;
  if (useDepsChanged([display]) && display) {
    setReduceMotion(display.reduce_motion ?? false);
  }

  const updateDisplayMutation = useMutation({
    mutationFn: (settings: { reduce_motion: boolean }) => api.updateDisplaySettings(settings),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["all-settings"] }),
    onError: (error: Error) => toast.error(error.message),
  });

  const handleReduceMotionToggle = (checked: boolean) => {
    setReduceMotion(checked);
    updateDisplayMutation.mutate({ reduce_motion: checked });
  };

  return (
    <SettingsPanel icon={<Accessibility />} title={t("accessibilityTitle")} description={tPanels("motionScope")}>
      {isLoading ? (
        <Skeleton className="h-6 w-48" />
      ) : (
        <Flex align="center" justify="between" gap="3" className="min-h-16">
          <Box className="min-w-0">
            <label htmlFor="reduce-motion" className="text-sm font-medium cursor-pointer">
              {t("reduceMotion")}
            </label>
            <Text id="reduce-motion-hint" size="xs" tone="muted" className="mt-0.5">
              {t("reduceMotionHint")}
            </Text>
          </Box>
          <Switch
            id="reduce-motion"
            aria-describedby="reduce-motion-hint"
            checked={reduceMotion}
            onCheckedChange={handleReduceMotionToggle}
            disabled={updateDisplayMutation.isPending}
            className="shrink-0"
          />
        </Flex>
      )}
    </SettingsPanel>
  );
}
