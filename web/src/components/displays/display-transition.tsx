"use client";

/**
 * A display's transition (plan D21/D22): chosen from its device's own menu,
 * stored as the board's `transition`.
 *
 * - An LED display (its model an LED matrix): FiestaUI's transition registry
 *   for that model, via `LedTransitionPicker` — entries the device cannot run
 *   are marked with why, so a Pixoo (two frames a second) offers only None:
 *   it snaps to each message, and says so.
 * - A split-flap display: "Default" (the install's Settings → Behavior
 *   choice), None, the strategies its output animates natively
 *   (`native_transitions`), and installed transition plugins while their
 *   beta is on. A cloud Vestaboard changes all at once; the note says so.
 */
import {
  Alert,
  AlertDescription,
  isLedTransitionId,
  type LedTransitionId,
  LedTransitionPicker,
  PageSection,
  Stack,
  Text,
  ToggleCard,
  ToggleCardGroup,
  transitionsForModel,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { Info, Sparkles } from "lucide-react";
import { useMemo } from "react";

import { useOutputs } from "@/components/settings/output-boards";
import { useTranslations } from "@/i18n/translations";
import type { BoardInstance } from "@/lib/api";
import { api } from "@/lib/api";
import { isLedModel, resolveBoardModel } from "@/lib/device-preview";

/** The split-flap strategies, in the menu's order, and their label keys (`transitionSettings.strategies`). */
const NATIVE_STRATEGIES: ReadonlyArray<{ value: string; key: string }> = [
  { value: "column", key: "column" },
  { value: "reverse-column", key: "reverseColumn" },
  { value: "edges-to-center", key: "edgesToCenter" },
  { value: "row", key: "row" },
  { value: "diagonal", key: "diagonal" },
  { value: "random", key: "random" },
];

/** The ToggleCardGroup value of "no choice of its own" (the board's `transition` unset). */
const DEFAULT_VALUE = "__default__";
const NONE = "none";
const PLUGIN_PREFIX = "plugin:";

export function DisplayTransition({
  board,
  onChange,
  disabled,
}: {
  board: BoardInstance;
  /** Save the display's choice; `null` follows the install's default. */
  onChange: (transition: string | null) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("displays.transition");
  const model = resolveBoardModel(board);

  return (
    <PageSection
      icon={<Sparkles />}
      title={t("title")}
      description={t("description")}
      data-testid="display-transition"
      contentClassName="space-y-3"
    >
      {isLedModel(model) ? (
        <LedTransitions board={board} model={model} onChange={onChange} />
      ) : (
        <SplitFlapTransitions board={board} onChange={onChange} disabled={disabled} />
      )}
    </PageSection>
  );
}

function LedTransitions({
  board,
  model,
  onChange,
}: {
  board: BoardInstance;
  model: NonNullable<ReturnType<typeof resolveBoardModel>>;
  onChange: (transition: string | null) => void;
}) {
  const t = useTranslations("displays.transition");
  const menu = useMemo(() => transitionsForModel(model), [model]);
  const runnable = menu.filter((entry) => entry.available);
  const stored = board.transition;
  const value: LedTransitionId | undefined = isLedTransitionId(stored) ? stored : undefined;
  const labels = useMemo(
    () => ({
      transitions: t("title"),
      deviceDefault: t("deviceDefault"),
      unavailable: t("unavailable"),
      runsAs: t("runsAs"),
      previewLabel: (name: string) => t("previewLabel", { name }),
    }),
    [t],
  );
  return (
    <Stack gap="3">
      {/* Only None runs here (a Pixoo shows two frames a second): it snaps. */}
      {runnable.length <= 1 && (
        <Alert data-testid="display-transition-snaps">
          <Info className="h-4 w-4" aria-hidden="true" />
          <AlertDescription>{t("snapNote")}</AlertDescription>
        </Alert>
      )}
      <LedTransitionPicker
        model={model}
        value={value}
        onValueChange={(id) => onChange(id)}
        columns="2"
        labels={labels}
      />
    </Stack>
  );
}

function SplitFlapTransitions({
  board,
  onChange,
  disabled,
}: {
  board: BoardInstance;
  onChange: (transition: string | null) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("displays.transition");
  const ts = useTranslations("transitionSettings");
  const { data: outputs } = useOutputs();
  const output = outputs?.find((o) => o.id === (board.output ?? "vestaboard"));
  const native = new Set(output?.capabilities.native_transitions ?? []);
  const strategies = NATIVE_STRATEGIES.filter((s) => native.has(s.value));

  // Transition plugins are beta-gated: offered only while the beta is on.
  const { data: beta } = useQuery({ queryKey: ["settings", "beta"], queryFn: () => api.getBetaSettings() });
  const pluginsOn = beta?.settings.transition_plugins_enabled ?? false;
  const { data: plugins } = useQuery({
    queryKey: ["plugins"],
    queryFn: () => api.listPlugins(),
    enabled: pluginsOn,
  });
  const transitionPlugins = pluginsOn ? (plugins?.plugins ?? []).filter((p) => p.plugin_type === "transition") : [];

  const stored = board.transition ?? null;
  const value = stored ?? DEFAULT_VALUE;
  // A stored plugin choice whose plugin is gone (or beta off): shown, not cleared.
  const orphan =
    stored?.startsWith(PLUGIN_PREFIX) && !transitionPlugins.some((p) => `${PLUGIN_PREFIX}${p.id}` === stored)
      ? stored
      : null;
  // A cloud Vestaboard takes one message at a time: no device animation.
  const config = (board.output_config ?? {}) as Record<string, unknown>;
  const cloud = (board.output ?? "vestaboard") === "vestaboard" && config.api_mode === "cloud";

  return (
    <Stack gap="3">
      {cloud && (
        <Alert data-testid="display-transition-cloud">
          <Info className="h-4 w-4" aria-hidden="true" />
          <AlertDescription>{t("cloudNote")}</AlertDescription>
        </Alert>
      )}
      <ToggleCardGroup
        columns="2"
        value={value}
        onValueChange={(next) => onChange(next === DEFAULT_VALUE ? null : next)}
        aria-label={t("title")}
        disabled={disabled}
      >
        <ToggleCard value={DEFAULT_VALUE} title={t("default")} description={t("defaultDescription")} />
        <ToggleCard value={NONE} title={ts("strategies.none.label")} description={ts("strategies.none.description")} />
        {strategies.map((s) => (
          <ToggleCard
            key={s.value}
            value={s.value}
            title={ts(`strategies.${s.key}.label`)}
            description={ts(`strategies.${s.key}.description`)}
          />
        ))}
        {transitionPlugins.map((p) => (
          <ToggleCard key={p.id} value={`${PLUGIN_PREFIX}${p.id}`} title={p.name} description={p.description} />
        ))}
        {orphan && <ToggleCard value={orphan} title={orphan.slice(PLUGIN_PREFIX.length)} disabled />}
      </ToggleCardGroup>
      {orphan && (
        <Text size="xs" tone="muted">
          {ts("unavailablePluginNote")}
        </Text>
      )}
    </Stack>
  );
}
