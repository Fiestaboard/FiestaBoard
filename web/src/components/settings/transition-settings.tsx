"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Sparkles, Info } from "lucide-react";
import { api, TransitionSettings as TransitionSettingsType } from "@/lib/api";

/** Human-friendly names and descriptions for each Vestaboard transition strategy. */
const STRATEGY_OPTIONS: {
  value: string | null;
  label: string;
  description: string;
}[] = [
  {
    value: null,
    label: "None",
    description: "No transition animation — the board updates all characters at once.",
  },
  {
    value: "column",
    label: "Wave",
    description: "Characters flip column-by-column from left to right.",
  },
  {
    value: "reverse-column",
    label: "Drift",
    description: "Characters flip column-by-column from right to left.",
  },
  {
    value: "edges-to-center",
    label: "Curtain",
    description: "Characters flip from both edges and meet in the center.",
  },
  {
    value: "row",
    label: "Row",
    description: "Characters flip row-by-row from top to bottom.",
  },
  {
    value: "diagonal",
    label: "Diagonal",
    description: "Characters flip in a diagonal wave from one corner to the other.",
  },
  {
    value: "random",
    label: "Random",
    description: "Characters flip in a random order for a playful effect.",
  },
];

export function TransitionSettings() {
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
      toast.success("Transition settings saved");
      setHasChanges(false);
    },
    onError: (error: Error) => {
      toast.error(`Failed to save transition settings: ${error.message}`);
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
          Board Transitions
        </CardTitle>
        <CardDescription>
          Choose how the board animates when updating to a new message. Transitions control the flip animation style of the characters on your Vestaboard.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Strategy Selector */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">Transition Style</Label>
          <div className="grid gap-2">
            {STRATEGY_OPTIONS.map((option) => {
              const isSelected = strategy === option.value;
              return (
                <button
                  key={option.value ?? "none"}
                  onClick={() => handleStrategyChange(option.value)}
                  className={`flex flex-col items-start p-3 rounded-md border text-left transition-colors ${
                    isSelected
                      ? "border-primary bg-primary/10"
                      : "border-muted hover:border-primary/50"
                  }`}
                >
                  <span className="text-sm font-medium">{option.label}</span>
                  <span className="text-xs text-muted-foreground mt-0.5">
                    {option.description}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Advanced options — only shown when a strategy is selected */}
        {strategy && (
          <div className="space-y-4 pt-2 border-t">
            <Label className="text-sm font-medium">Advanced Options</Label>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Step Interval */}
              <div className="space-y-1.5">
                <Label htmlFor="step-interval" className="text-xs">
                  Step Interval (ms)
                </Label>
                <Input
                  id="step-interval"
                  type="number"
                  min={0}
                  placeholder="Default"
                  value={stepIntervalMs}
                  onChange={(e) => handleStepIntervalChange(e.target.value)}
                  className="w-full"
                />
                <p className="text-[11px] text-muted-foreground">
                  Delay between each animation step. Leave empty for the board default.
                </p>
              </div>

              {/* Step Size */}
              <div className="space-y-1.5">
                <Label htmlFor="step-size" className="text-xs">
                  Step Size
                </Label>
                <Input
                  id="step-size"
                  type="number"
                  min={1}
                  placeholder="Default"
                  value={stepSize}
                  onChange={(e) => handleStepSizeChange(e.target.value)}
                  className="w-full"
                />
                <p className="text-[11px] text-muted-foreground">
                  How many rows or columns animate at once. Leave empty for the board default.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Info note */}
        <div className="flex items-start gap-2 p-2.5 rounded-md bg-muted/50 text-xs text-muted-foreground">
          <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <span>
            Transitions are supported on the <strong>Local API</strong> only. If your board is configured to use the Cloud API, transition settings will have no effect. Individual pages can also override this default in the page builder.
          </span>
        </div>

        {/* Saving indicator */}
        {updateMutation.isPending && (
          <div className="flex items-center justify-center gap-2 pt-2 text-xs text-muted-foreground">
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span>Saving...</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
