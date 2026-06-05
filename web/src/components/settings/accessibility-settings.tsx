"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Accessibility } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
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
          <div className="flex items-center gap-3">
            <Switch
              id="reduce-motion"
              checked={reduceMotion}
              onCheckedChange={handleReduceMotionToggle}
              disabled={updateDisplayMutation.isPending}
            />
            <div>
              <label htmlFor="reduce-motion" className="text-sm font-medium cursor-pointer">
                {t("reduceMotion")}
              </label>
              <p className="text-xs text-muted-foreground mt-0.5">{t("reduceMotionHint")}</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
