"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Puzzle } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

export function PluginSettingsCard() {
  const t = useTranslations("pluginSettings");
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "plugins"],
    queryFn: () => api.getPluginSettings(),
  });

  const mutation = useMutation({
    mutationFn: (auto_update: boolean) =>
      api.updatePluginSettings({ auto_update }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "plugins"] });
      queryClient.invalidateQueries({ queryKey: ["settings", "all"] });
      toast.success(t("savedToast"));
    },
    onError: (err: Error) => {
      toast.error(t("saveFailedToast", { error: err.message }));
    },
  });

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Puzzle className="h-4 w-4" />
            {t("title")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Puzzle className="h-4 w-4" />
          {t("title")}
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-start justify-between gap-4 rounded-md border p-4">
          <div className="space-y-1">
            <span className="font-medium">{t("autoUpdateLabel")}</span>
            <p className="text-sm text-muted-foreground">
              {t("autoUpdateDescription")}
            </p>
          </div>
          <Switch
            checked={data.settings.auto_update}
            disabled={mutation.isPending}
            onCheckedChange={(checked) => mutation.mutate(checked)}
            aria-label={t("autoUpdateLabel")}
          />
        </div>
      </CardContent>
    </Card>
  );
}
