"use client";

import {
  Box,
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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

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

export function TransitionSettings() {
  const t = useTranslations("transitionSettings");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const { data: allSettings, isLoading } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const transitions = allSettings?.transitions;

  const [strategy, setStrategy] = useState<string | null>(null);
  const [stepIntervalMs, setStepIntervalMs] = useState<number | "">("");
  const [stepSize, setStepSize] = useState<number | "">("");
  const [hasChanges, setHasChanges] = useState(false);

  // Sync local state when settings load
  useEffect(() => {
    if (transitions) {
      setStrategy(transitions.strategy);
      setStepIntervalMs(transitions.step_interval_ms ?? "");
      setStepSize(transitions.step_size ?? "");
      setHasChanges(false);
    }
  }, [transitions]);

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
          <Flex wrap gap="2">
            {STRATEGY_VALUES.map((option) => {
              const isSelected = strategy === option.value;
              return (
                <button
                  key={option.value ?? "none"}
                  onClick={() => handleStrategyChange(option.value)}
                  className={`px-3 py-1.5 rounded-md border text-xs font-medium transition-colors ${
                    isSelected
                      ? "border-brand bg-brand/10 text-brand"
                      : "border-muted hover:border-brand/50 text-foreground"
                  }`}
                >
                  {t(`strategies.${option.key}.label`)}
                </button>
              );
            })}
          </Flex>
          {/* Description of selected strategy */}
          {(() => {
            const selected = STRATEGY_VALUES.find((o) => o.value === strategy);
            return selected ? (
              <Text size="xs" tone="muted">
                {t(`strategies.${selected.key}.description`)}
              </Text>
            ) : null;
          })()}
        </Stack>

        {/* Advanced options — only shown when a strategy is selected */}
        {strategy && (
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

        {/* Saving indicator */}
        {updateMutation.isPending && (
          <Flex align="center" justify="center" gap="2" className="pt-2 text-xs text-muted-foreground">
            <Box className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <Text as="span" size="xs" tone="muted">
              {tCommon("saving")}
            </Text>
          </Flex>
        )}
      </CardContent>
    </Card>
  );
}
