"use client";

import { Badge, Flex, PageSection, Skeleton, Stack, Switch, Text } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FlaskConical, Tv, Wand2 } from "lucide-react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api } from "@/lib/api";

/**
 * Settings → Beta section.
 *
 * Exposes the experimental toggles: Transition Plugins (Beta) and Output
 * Plugins (Beta). Both take effect without a restart.
 */
export function BetaSettings() {
  const t = useTranslations("betaSettings");
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["settings", "beta"],
    queryFn: () => api.getBetaSettings(),
  });

  const transitionsMutation = useMutation({
    mutationFn: (next: boolean) => api.updateBetaSettings({ transition_plugins_enabled: next }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "beta"] });
      queryClient.invalidateQueries({ queryKey: ["settings", "all"] });
      toast.success(t("savedToast"));
    },
    onError: (err: Error) => {
      toast.error(t("saveFailedToast", { error: err.message }));
    },
  });

  const outputsMutation = useMutation({
    mutationFn: (next: boolean) => api.updateBetaSettings({ output_plugins_enabled: next }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "beta"] });
      queryClient.invalidateQueries({ queryKey: ["settings", "all"] });
      toast.success(t("savedToast"));
    },
    onError: (err: Error) => {
      toast.error(t("saveFailedToast", { error: err.message }));
    },
  });

  if (isLoading || !data) {
    return (
      <PageSection icon={<FlaskConical />} title={t("title")}>
        <Skeleton className="h-16 w-full" />
      </PageSection>
    );
  }

  const transitionsEnabled = data.settings.transition_plugins_enabled;
  // Absent from a server that predates the flag: off.
  const outputsEnabled = data.settings.output_plugins_enabled ?? false;

  return (
    <PageSection
      icon={<FlaskConical />}
      title={
        <>
          {t("title")}
          <Badge variant="outline" className="ml-1 text-[10px] uppercase tracking-wide">
            {t("betaBadge")}
          </Badge>
        </>
      }
      description={t("description")}
      contentClassName="space-y-4"
      {...anchorProps("settings.beta")}
    >
      <Flex align="start" justify="between" gap="4" className="rounded-md border p-4">
        <Stack gap="1">
          <Flex align="center" gap="2">
            <Wand2 className="h-4 w-4 text-muted-foreground" />
            <Text as="span" weight="medium">
              {t("transitionsLabel")}
            </Text>
          </Flex>
          <Text tone="muted">{t("transitionsDescription")}</Text>
          <Flex align="start" gap="1.5" className="text-xs text-muted-foreground pt-1">
            <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <Text as="span" size="xs" tone="muted">
              {t("transitionsWarning")}
            </Text>
          </Flex>
        </Stack>
        <Switch
          checked={transitionsEnabled}
          {...anchorProps("settings.beta.transition_plugins_enabled")}
          disabled={transitionsMutation.isPending}
          onCheckedChange={(checked) => transitionsMutation.mutate(checked)}
          aria-label={t("transitionsLabel")}
        />
      </Flex>

      <Flex align="start" justify="between" gap="4" className="rounded-md border p-4">
        <Stack gap="1">
          <Flex align="center" gap="2">
            <Tv className="h-4 w-4 text-muted-foreground" />
            <Text as="span" weight="medium">
              {t("outputsLabel")}
            </Text>
          </Flex>
          <Text tone="muted">{t("outputsDescription")}</Text>
          <Flex align="start" gap="1.5" className="text-xs text-muted-foreground pt-1">
            <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <Text as="span" size="xs" tone="muted">
              {t("outputsWarning")}
            </Text>
          </Flex>
        </Stack>
        <Switch
          checked={outputsEnabled}
          {...anchorProps("settings.beta.output_plugins_enabled")}
          disabled={outputsMutation.isPending}
          onCheckedChange={(checked) => outputsMutation.mutate(checked)}
          aria-label={t("outputsLabel")}
        />
      </Flex>
    </PageSection>
  );
}
