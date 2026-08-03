"use client";

import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Flex,
  Skeleton,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Puzzle, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export function PluginSettingsCard() {
  const t = useTranslations("pluginSettings");
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "plugins"],
    queryFn: () => api.getPluginSettings(),
  });

  const mutation = useMutation({
    mutationFn: (auto_update: boolean) => api.updatePluginSettings({ auto_update }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "plugins"] });
      queryClient.invalidateQueries({ queryKey: ["settings", "all"] });
      toast.success(t("savedToast"));
    },
    onError: (err: Error) => {
      toast.error(t("saveFailedToast", { error: err.message }));
    },
  });

  const checkMutation = useMutation({
    mutationFn: () => api.triggerPluginUpdateCheck(),
    onSuccess: (result) => {
      const count = result.updates_available.length;
      if (count > 0) {
        toast.success(t("toastUpdatesFound", { count }));
      } else {
        toast.success(t("toastNoUpdates"));
      }
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-updates"] });
    },
    onError: (err: Error) => {
      toast.error(t("toastCheckFailed", { error: err.message }));
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
      <CardContent className="space-y-3">
        <Flex align="start" justify="between" gap="4" className="rounded-md border p-4">
          <Stack gap="1">
            <Text as="span" weight="medium">
              {t("autoUpdateLabel")}
            </Text>
            <Text tone="muted">{t("autoUpdateDescription")}</Text>
          </Stack>
          <Switch
            checked={data.settings.auto_update}
            disabled={mutation.isPending}
            onCheckedChange={(checked) => mutation.mutate(checked)}
            aria-label={t("autoUpdateLabel")}
          />
        </Flex>
        <Flex align="start" justify="between" gap="4" className="rounded-md border p-4">
          <Stack gap="1">
            <Text as="span" weight="medium">
              {t("checkForUpdates")}
            </Text>
            <Text tone="muted">{t("checkDescription")}</Text>
          </Stack>
          <Button
            variant="outline"
            size="sm"
            onClick={() => checkMutation.mutate()}
            disabled={checkMutation.isPending}
            className="gap-2 shrink-0"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", checkMutation.isPending && "animate-spin")} />
            {checkMutation.isPending ? t("checking") : t("checkForUpdates")}
          </Button>
        </Flex>
      </CardContent>
    </Card>
  );
}
