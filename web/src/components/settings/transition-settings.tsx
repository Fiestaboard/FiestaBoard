"use client";

import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Flex,
  Grid,
  Input,
  Label,
  Skeleton,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useTranslations } from "@/i18n/translations";
import type { TransitionSettings as TransitionSettingsType } from "@/lib/api";
import { api } from "@/lib/api";

const STRATEGY_VALUES: {
  value: string | null;
  key: "none" | "column" | "reverseColumn" | "edgesToCenter" | "row" | "diagonal" | "random";
}[] = [
  { value: null, key: "none" },
  { value: "column", key: "column" },
  { value: "reverse-column", key: "reverseColumn" },
  { value: "edges-to-center", key: "edgesToCenter" },
  { value: "row", key: "row" },
  { value: "diagonal", key: "diagonal" },
  { value: "random", key: "random" },
];

/** Prefix the backend uses for transition-plugin strategies (`plugin:<id>`). */
const PLUGIN_PREFIX = "plugin:";

const OPTION_BASE_CLASS = "px-3 py-1.5 rounded-md border text-xs font-medium transition-colors";
const OPTION_SELECTED_CLASS = "border-brand bg-brand/10 text-brand";
const OPTION_IDLE_CLASS = "border-muted hover:border-brand/50 text-foreground";

export function TransitionSettings() {
  const t = useTranslations("transitionSettings");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const { data: allSettings, isLoading } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const transitions = allSettings?.transitions;

  // Transition plugins are beta-gated: the backend rejects `plugin:` strategies
  // (and 404s the plugin list) while the flag is off, so don't even fetch.
  // Same queryKey as the Transition Lab page so the cache is shared.
  const betaQuery = useQuery({
    queryKey: ["settings", "beta"],
    queryFn: () => api.getBetaSettings(),
  });
  const betaEnabled = betaQuery.data?.settings.transition_plugins_enabled ?? false;

  const pluginsQuery = useQuery({
    queryKey: ["transition-plugins"],
    queryFn: () => api.listTransitionPlugins(),
    enabled: betaEnabled,
  });
  const plugins = useMemo(() => pluginsQuery.data?.plugins ?? [], [pluginsQuery.data]);

  const [strategy, setStrategy] = useState<string | null>(null);
  const [stepIntervalMs, setStepIntervalMs] = useState<number | "">("");
  const [stepSize, setStepSize] = useState<number | "">("");
  const [hasChanges, setHasChanges] = useState(false);

  // Sync local state when settings load. Done during render rather than in an
  // effect so the stored strategy is selected in the first commit
  // (react-hooks/set-state-in-effect, issue #1568).
  if (useDepsChanged([transitions]) && transitions) {
    setStrategy(transitions.strategy);
    setStepIntervalMs(transitions.step_interval_ms ?? "");
    setStepSize(transitions.step_size ?? "");
    setHasChanges(false);
  }

  const updateMutation = useMutation({
    mutationFn: (settings: Partial<TransitionSettingsType>) => api.updateTransitionSettings(settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
      toast.success(t("toastSaved"));
      setHasChanges(false);
    },
    onError: (error: Error) => {
      toast.error(t("toastSaveFailed", { error: error.message }));
    },
  });

  // Auto-save on changes
  useEffect(() => {
    if (!hasChanges || updateMutation.isPending) return;

    const timeoutId = setTimeout(() => {
      updateMutation.mutate({
        strategy,
        step_interval_ms: stepIntervalMs === "" ? null : stepIntervalMs,
        step_size: stepSize === "" ? null : stepSize,
      });
    }, 1000);

    return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategy, stepIntervalMs, stepSize, hasChanges]);

  const handleStrategyChange = (value: string | null) => {
    setStrategy(value);
    setHasChanges(true);
  };

  const handleStepIntervalChange = (value: string) => {
    if (value === "") {
      setStepIntervalMs("");
    } else {
      const num = parseInt(value, 10);
      setStepIntervalMs(isNaN(num) ? "" : num);
    }
    setHasChanges(true);
  };

  const handleStepSizeChange = (value: string) => {
    if (value === "") {
      setStepSize("");
    } else {
      const num = parseInt(value, 10);
      setStepSize(isNaN(num) ? "" : num);
    }
    setHasChanges(true);
  };

  // `plugin:<id>` strategies are rendered frame-by-frame by FiestaBoard rather
  // than handed to the Vestaboard local API, so they behave differently from
  // the built-ins: no step interval/size, and no Local-API-only caveat.
  const selectedPluginId = strategy?.startsWith(PLUGIN_PREFIX) ? strategy.slice(PLUGIN_PREFIX.length) : null;
  const selectedPlugin = selectedPluginId ? (plugins.find((p) => p.id === selectedPluginId) ?? null) : null;
  // A saved plugin strategy whose plugin isn't in the list — beta turned off, or
  // the plugin was uninstalled. Show it rather than silently clearing it.
  const orphanPluginId = selectedPluginId && !selectedPlugin ? selectedPluginId : null;
  const showPluginGroup = betaEnabled && plugins.length > 0;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-64" />
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="h-4 w-4" />
          {t("title")}
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Strategy Selector */}
        <Stack gap="2">
          <Label className="text-sm font-medium">{t("transitionStyle")}</Label>

          {/* Group headings only appear once there is a second group to
              disambiguate from — otherwise the card looks exactly as before. */}
          {showPluginGroup && (
            <Text size="xs" tone="muted" className="font-medium">
              {t("builtInGroup")}
            </Text>
          )}
          <Flex wrap gap="2">
            {STRATEGY_VALUES.map((option) => {
              const isSelected = strategy === option.value;
              return (
                <button
                  key={option.value ?? "none"}
                  onClick={() => handleStrategyChange(option.value)}
                  className={`${OPTION_BASE_CLASS} ${isSelected ? OPTION_SELECTED_CLASS : OPTION_IDLE_CLASS}`}
                >
                  {t(`strategies.${option.key}.label`)}
                </button>
              );
            })}
          </Flex>

          {showPluginGroup && (
            <>
              <Flex align="center" gap="2" className="pt-2">
                <Text size="xs" tone="muted" className="font-medium">
                  {t("pluginsGroup")}
                </Text>
                <Badge variant="secondary">{t("pluginsBetaBadge")}</Badge>
              </Flex>
              <Flex wrap gap="2">
                {plugins.map((plugin) => {
                  const isSelected = selectedPluginId === plugin.id;
                  return (
                    <button
                      key={plugin.id}
                      onClick={() => handleStrategyChange(`${PLUGIN_PREFIX}${plugin.id}`)}
                      className={`${OPTION_BASE_CLASS} ${isSelected ? OPTION_SELECTED_CLASS : OPTION_IDLE_CLASS}`}
                    >
                      {plugin.name}
                    </button>
                  );
                })}
              </Flex>
            </>
          )}

          {orphanPluginId && (
            <Flex wrap gap="2">
              {/* Already selected, so there is nothing to click toward — it
                  exists purely so the setting stays visible and the user can
                  choose a different option instead of it. */}
              <button type="button" aria-pressed className={`${OPTION_BASE_CLASS} ${OPTION_SELECTED_CLASS}`}>
                {orphanPluginId}
              </button>
            </Flex>
          )}

          {/* Description of selected strategy */}
          {(() => {
            if (selectedPlugin) {
              return (
                <Text size="xs" tone="muted">
                  {selectedPlugin.description}
                </Text>
              );
            }
            if (orphanPluginId) {
              return (
                <Text size="xs" tone="muted">
                  {t("unavailablePluginNote")}
                </Text>
              );
            }
            const selected = STRATEGY_VALUES.find((o) => o.value === strategy);
            return selected ? (
              <Text size="xs" tone="muted">
                {t(`strategies.${selected.key}.description`)}
              </Text>
            ) : null;
          })()}
        </Stack>

        {/* Advanced options — only for built-in strategies. Step interval and
            step size are forwarded to the Vestaboard local API, which never
            sees a plugin transition, so they are ignored there. */}
        {strategy && !selectedPluginId && (
          <Stack gap="4" className="pt-2 border-t">
            <Label className="text-sm font-medium">{t("advancedOptions")}</Label>

            <Grid cols="1" sm="2" gap="4">
              {/* Step Interval */}
              <Stack gap="1.5">
                <Label htmlFor="step-interval" className="text-xs">
                  {t("stepIntervalLabel")}
                </Label>
                <Input
                  id="step-interval"
                  type="number"
                  min={0}
                  placeholder={t("stepIntervalPlaceholder")}
                  value={stepIntervalMs}
                  onChange={(e) => handleStepIntervalChange(e.target.value)}
                  className="w-full"
                />
                <Text size="xs" tone="muted">
                  {t("stepIntervalDescription")}
                </Text>
              </Stack>

              {/* Step Size */}
              <Stack gap="1.5">
                <Label htmlFor="step-size" className="text-xs">
                  {t("stepSizeLabel")}
                </Label>
                <Input
                  id="step-size"
                  type="number"
                  min={1}
                  placeholder={t("stepSizePlaceholder")}
                  value={stepSize}
                  onChange={(e) => handleStepSizeChange(e.target.value)}
                  className="w-full"
                />
                <Text size="xs" tone="muted">
                  {t("stepSizeDescription")}
                </Text>
              </Stack>
            </Grid>
          </Stack>
        )}

        {/* Info note */}
        <Flex align="start" gap="2" className="p-2.5 rounded-md bg-muted/50 text-xs text-muted-foreground">
          <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <Text as="span" size="xs" tone="muted">
            {t("localApiNote")}
          </Text>
        </Flex>

        {/* Plugin transitions are repeated full-grid sends, not local-API
            transition hints, so the note above does not apply to them. */}
        {selectedPluginId && (
          <Flex align="start" gap="2" className="p-2.5 rounded-md bg-muted/50 text-xs text-muted-foreground">
            <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <Text as="span" size="xs" tone="muted">
              {t("pluginNote")}
            </Text>
          </Flex>
        )}

        {/* Saving indicator */}
        {updateMutation.isPending && (
          <Flex align="center" justify="center" gap="2" className="pt-2 text-xs text-muted-foreground">
            <Spinner size="sm" className="size-3 text-primary" label={null} />
            <Text as="span" size="xs" tone="muted">
              {tCommon("saving")}
            </Text>
          </Flex>
        )}
      </CardContent>
    </Card>
  );
}
