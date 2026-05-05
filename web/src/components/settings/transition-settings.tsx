"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Sparkles, Info } from "lucide-react";
import { api, TransitionSettings as TransitionSettingsType } from "@/lib/api";

const STRATEGY_VALUES: { value: string | null; key: "none" | "column" | "reverseColumn" | "edgesToCenter" | "row" | "diagonal" | "random" }[] = [
  { value: null, key: "none" },
  { value: "column", key: "column" },
  { value: "reverse-column", key: "reverseColumn" },
  { value: "edges-to-center", key: "edgesToCenter" },
  { value: "row", key: "row" },
  { value: "diagonal", key: "diagonal" },
  { value: "random", key: "random" },
  { value: "quietLibrary", key: "quietLibrary" },
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
    mutationFn: (settings: Partial<TransitionSettingsType>) =>
      api.updateTransitionSettings(settings),
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
        <CardDescription>
          {t("description")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Strategy Selector */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">{t("transitionStyle")}</Label>
          <div className="flex flex-wrap gap-2">
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
          </div>
          {/* Description of selected strategy */}
          {(() => {
            const selected = STRATEGY_VALUES.find((o) => o.value === strategy);
            return selected ? (
              <p className="text-xs text-muted-foreground">{t(`strategies.${selected.key}.description`)}</p>
            ) : null;
          })()}
        </div>

        {/* Advanced options — only shown when a strategy is selected */}
        {strategy && (
          <div className="space-y-4 pt-2 border-t">
            <Label className="text-sm font-medium">{t("advancedOptions")}</Label>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Step Interval */}
              <div className="space-y-1.5">
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
                <p className="text-[11px] text-muted-foreground">
                  {t("stepIntervalDescription")}
                </p>
              </div>

              {/* Step Size */}
              <div className="space-y-1.5">
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
                <p className="text-[11px] text-muted-foreground">
                  {t("stepSizeDescription")}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Info note */}
        <div className="flex items-start gap-2 p-2.5 rounded-md bg-muted/50 text-xs text-muted-foreground">
          <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <span>
            {t("localApiNote")}
          </span>
        </div>

        {/* Saving indicator */}
        {updateMutation.isPending && (
          <div className="flex items-center justify-center gap-2 pt-2 text-xs text-muted-foreground">
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span>{tCommon("saving")}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
