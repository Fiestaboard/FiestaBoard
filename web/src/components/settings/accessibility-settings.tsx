"use client";

import { Box, Card, CardContent, CardDescription, CardHeader, CardTitle, Flex, Skeleton, Switch, Text } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Accessibility } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

export function AccessibilitySettings() {
  const t = useTranslations("profile");
  const queryClient = useQueryClient();

  const [reduceMotion, setReduceMotion] = useState(false);

  const { data: allSettings, isLoading } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  useEffect(() => {
    const display = allSettings?.display;
    if (display) setReduceMotion(display.reduce_motion ?? false);
  }, [allSettings?.display]);

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
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Accessibility className="h-4 w-4" />
          {t("accessibilityTitle")}
        </CardTitle>
        <CardDescription>{t("accessibilityDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-6 w-48" />
        ) : (
          <Flex align="center" gap="3">
            <Switch
              id="reduce-motion"
              checked={reduceMotion}
              onCheckedChange={handleReduceMotionToggle}
              disabled={updateDisplayMutation.isPending}
            />
            <Box>
              <label htmlFor="reduce-motion" className="text-sm font-medium cursor-pointer">
                {t("reduceMotion")}
              </label>
              <Text size="xs" tone="muted" className="mt-0.5">
                {t("reduceMotionHint")}
              </Text>
            </Box>
          </Flex>
        )}
      </CardContent>
    </Card>
  );
}
