"use client";

/**
 * A display's transition (plan D21/D22): chosen from its device's own menu,
 * stored on the board as `transition`, `transition_step_interval_ms` and
 * `transition_step_size`. Every display owns its transition (settings v6);
 * there is no install-wide default to fall back to.
 *
 * - An LED display (its model an LED matrix): FiestaUI's transition registry
 *   for that model, in a compact selector — entries the device cannot run
 *   are marked with why, so a device that pushes two frames a second (an
 *   AWTRIX clock) offers only None: it snaps to each message, and says so.
 * - A split-flap display: None, the strategies its output animates natively
 *   (`native_transitions`) with their speed (step interval and step size),
 *   and installed transition plugins while they are on. The transition
 *   plugins switch is install-wide (it applies to every display) and shows
 *   only where frame-driven transitions can run. A cloud Vestaboard changes
 *   all at once; the note says so.
 */
import {
  Alert,
  AlertDescription,
  Badge,
  Box,
  defaultTransitionIdForModel,
  Flex,
  Grid,
  Input,
  Label,
  PageSection,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Switch,
  Text,
  transitionsForModel,
} from "@fiestaboard/ui";
import { Info, Sparkles } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { toast } from "sonner";

import { useOutputs } from "@/components/settings/output-boards";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { usePluginSettings, useUpdatePluginSettings } from "@/hooks/use-plugin-settings";
import { useTransitionPlugins } from "@/hooks/use-transition-plugins";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import type { BoardInstance } from "@/lib/api";
import { isLedModel, resolveBoardModel } from "@/lib/device-preview";

import { TransitionPreview } from "./transition-preview";

/** The split-flap strategies, in the menu's order, and their label keys (`transitionSettings.strategies`). */
const NATIVE_STRATEGIES: ReadonlyArray<{ value: string; key: string }> = [
  { value: "column", key: "column" },
  { value: "reverse-column", key: "reverseColumn" },
  { value: "edges-to-center", key: "edgesToCenter" },
  { value: "row", key: "row" },
  { value: "diagonal", key: "diagonal" },
  { value: "random", key: "random" },
];

const NONE = "none";
const PLUGIN_PREFIX = "plugin:";

/** What a display's transition section saves: the board fields it owns. */
export type DisplayTransitionUpdate = Pick<
  BoardInstance,
  "transition" | "transition_step_interval_ms" | "transition_step_size"
>;

export function DisplayTransition({
  board,
  onChange,
  disabled,
}: {
  board: BoardInstance;
  /** Save some of the display's transition fields. */
  onChange: (updates: Partial<DisplayTransitionUpdate>) => void;
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
      {...anchorProps("settings.transitions")}
    >
      {isLedModel(model) ? (
        <LedTransitions board={board} model={model} onChange={onChange} disabled={disabled} />
      ) : (
        <SplitFlapTransitions board={board} onChange={onChange} disabled={disabled} />
      )}
    </PageSection>
  );
}

function TransitionSelector({
  value,
  onChange,
  options,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string; disabled?: boolean }[];
  disabled?: boolean;
}) {
  const t = useTranslations("displays.transition");
  const id = useId();
  return (
    <Stack gap="1.5" className="min-w-0">
      <Label htmlFor={id}>{t("title")}</Label>
      <Select
        value={value}
        onValueChange={(next) => {
          if (next) onChange(next);
        }}
        disabled={disabled}
      >
        <SelectTrigger id={id} className="min-w-0 w-full sm:max-w-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Stack>
  );
}

function LedTransitions({
  board,
  model,
  onChange,
  disabled,
}: {
  board: BoardInstance;
  model: NonNullable<ReturnType<typeof resolveBoardModel>>;
  onChange: (updates: Partial<DisplayTransitionUpdate>) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("displays.transition");
  const menu = useMemo(() => transitionsForModel(model), [model]);
  const value = board.transition || "default";
  const selected = menu.find(
    (entry) => entry.id === (value === "default" ? defaultTransitionIdForModel(model) : value),
  );
  const options: { value: string; label: string; disabled?: boolean }[] = [
    { value: "default", label: t("deviceDefault") },
    ...menu.map((entry) => ({ value: entry.id, label: entry.entry.label, disabled: !entry.available })),
  ];
  if (!options.some((option) => option.value === value))
    options.push({ value, label: t("savedUnavailable", { name: value }), disabled: true });
  return (
    <Stack gap="3">
      {menu.filter((entry) => entry.available).length <= 1 && (
        <Alert data-testid="display-transition-snaps">
          <Info className="h-4 w-4" aria-hidden="true" />
          <AlertDescription>{t("snapNote")}</AlertDescription>
        </Alert>
      )}
      <Box className="grid min-w-0 grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <Stack gap="2" className="min-w-0">
          <TransitionSelector
            value={value}
            options={options}
            onChange={(id) => onChange({ transition: id === "default" ? null : id })}
            disabled={disabled}
          />
          {selected && (
            <Text size="sm" tone="muted">
              {selected.entry.description}
            </Text>
          )}
          {selected?.reason && (
            <Text size="xs" tone="muted">
              {selected.available ? t("runsAs") : t("unavailable")}: {selected.reason}
            </Text>
          )}
        </Stack>
        {selected?.spec && (
          <TransitionPreview key={`${board.id}:${value}`} value={value} model={model} spec={selected.spec} />
        )}
        {!selected && (
          <Text size="sm" tone="muted">
            {t("unavailable")}
          </Text>
        )}
      </Box>
    </Stack>
  );
}

function SplitFlapTransitions({
  board,
  onChange,
  disabled,
}: {
  board: BoardInstance;
  onChange: (updates: Partial<DisplayTransitionUpdate>) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("displays.transition");
  const ts = useTranslations("transitionSettings");
  const { data: outputs } = useOutputs();
  const output = outputs?.find((o) => o.id === (board.output ?? "vestaboard"));
  const native = new Set(output?.capabilities.native_transitions ?? []);
  const strategies = NATIVE_STRATEGIES.filter((s) => native.has(s.value));

  // A cloud Vestaboard takes one message at a time: no device animation.
  const config = (board.output_config ?? {}) as Record<string, unknown>;
  const cloud = (board.output ?? "vestaboard") === "vestaboard" && config.api_mode === "cloud";
  // Transition plugins drive the board frame by frame, which needs an output
  // that takes frames (not a cloud Vestaboard, which changes all at once).
  const framesRun = !cloud && output !== undefined && output.capabilities.animation !== "none";

  // Transition plugins are beta-gated: offered only while they are on.
  const { data: pluginSettings } = usePluginSettings();
  const pluginsOn = pluginSettings?.transition_plugins_enabled ?? false;
  const installedTransitionPlugins = useTransitionPlugins(pluginsOn);
  const transitionPlugins = pluginsOn ? installedTransitionPlugins : [];

  // Unset reads as None: every split-flap display starts with a choice
  // (settings v6), and the runtime runs an unset one as no transition.
  const value = board.transition || NONE;
  // A stored plugin choice whose plugin is gone (or turned off): shown, not cleared.
  const orphan =
    value.startsWith(PLUGIN_PREFIX) && !transitionPlugins.some((p) => `${PLUGIN_PREFIX}${p.id}` === value)
      ? value
      : null;
  // Speed is forwarded to the device with a native strategy only: None is a
  // plain write, and a plugin paces its own frames.
  const showSpeed = !cloud && native.has(value);

  return (
    <Stack gap="3">
      {cloud && (
        <Alert data-testid="display-transition-cloud">
          <Info className="h-4 w-4" aria-hidden="true" />
          <AlertDescription>{t("cloudNote")}</AlertDescription>
        </Alert>
      )}
      <Box className="grid min-w-0 grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <Stack gap="3" className="min-w-0">
          <TransitionSelector
            value={value}
            onChange={(next) => onChange({ transition: next })}
            disabled={disabled}
            options={[
              { value: NONE, label: ts("strategies.none.label") },
              ...strategies.map((s) => ({ value: s.value, label: ts(`strategies.${s.key}.label`), disabled: cloud })),
              ...transitionPlugins.map((p) => ({
                value: `${PLUGIN_PREFIX}${p.id}`,
                label: p.name,
                disabled: !framesRun,
              })),
              ...(![
                NONE,
                ...strategies.map((s) => s.value),
                ...transitionPlugins.map((p) => `${PLUGIN_PREFIX}${p.id}`),
              ].includes(value)
                ? [{ value, label: t("savedUnavailable", { name: value.replace(PLUGIN_PREFIX, "") }), disabled: true }]
                : []),
            ]}
          />
          <Text size="sm" tone="muted">
            {value === NONE
              ? ts("strategies.none.description")
              : strategies.some((s) => s.value === value)
                ? ts(`strategies.${strategies.find((s) => s.value === value)!.key}.description`)
                : transitionPlugins.find((p) => `${PLUGIN_PREFIX}${p.id}` === value)?.description}
          </Text>
          {orphan && (
            <Text size="xs" tone="muted">
              {ts("unavailablePluginNote")}
            </Text>
          )}
          {showSpeed && <TransitionSpeed board={board} onChange={onChange} disabled={disabled} />}
        </Stack>
        <TransitionPreview
          key={`${board.id}:${value}`}
          value={value}
          native={native.has(value)}
          cloud={cloud}
          interval={board.transition_step_interval_ms ?? 50}
          size={board.transition_step_size ?? 1}
        />
      </Box>
      {framesRun && <TransitionPluginsSwitch boardId={board.id} />}
    </Stack>
  );
}

/** The longest step interval a display takes, as a page's (src/devices.py TRANSITION_SPEED_BOUNDS). */
const MAX_STEP_INTERVAL_MS = 5000;

/** A number field's text as the board field: empty is the device default (`null`); out of range is `undefined`. */
function parseSpeed(text: string, minimum: number, maximum = Infinity): number | null | undefined {
  if (text.trim() === "") return null;
  const n = Number(text);
  if (!Number.isInteger(n) || n < minimum || n > maximum) return undefined;
  return n;
}

function TransitionSpeed({
  board,
  onChange,
  disabled,
}: {
  board: BoardInstance;
  onChange: (updates: Partial<DisplayTransitionUpdate>) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("displays.transition");
  const stored = {
    interval: board.transition_step_interval_ms ?? null,
    size: board.transition_step_size ?? null,
  };
  const [interval, setIntervalText] = useState(stored.interval === null ? "" : String(stored.interval));
  const [size, setSizeText] = useState(stored.size === null ? "" : String(stored.size));
  // Follow a save (or another tab's) without an effect (react-hooks/set-state-in-effect).
  if (useDepsChanged([stored.interval, stored.size])) {
    setIntervalText(stored.interval === null ? "" : String(stored.interval));
    setSizeText(stored.size === null ? "" : String(stored.size));
  }

  const intervalId = `transition-step-interval-${board.id}`;
  const sizeId = `transition-step-size-${board.id}`;
  const intervalValue = parseSpeed(interval, 0, MAX_STEP_INTERVAL_MS);
  const sizeValue = parseSpeed(size, 1);

  const commitInterval = () => {
    if (intervalValue === undefined || intervalValue === stored.interval) return;
    onChange({ transition_step_interval_ms: intervalValue });
  };
  const commitSize = () => {
    if (sizeValue === undefined || sizeValue === stored.size) return;
    onChange({ transition_step_size: sizeValue });
  };

  return (
    <Stack gap="3" className="pt-2 border-t" data-testid="display-transition-speed">
      <Text as="span" weight="medium" size="sm">
        {t("speedTitle")}
      </Text>
      <Grid cols="1" sm="2" gap="4">
        <Stack gap="1.5">
          <Label htmlFor={intervalId} className="text-xs">
            {t("stepIntervalLabel")}
          </Label>
          <Input
            id={intervalId}
            type="number"
            inputMode="numeric"
            min={0}
            max={MAX_STEP_INTERVAL_MS}
            placeholder={t("stepIntervalPlaceholder")}
            value={interval}
            disabled={disabled}
            aria-invalid={intervalValue === undefined || undefined}
            onChange={(e) => setIntervalText(e.target.value)}
            onBlur={commitInterval}
            onKeyDown={(e) => e.key === "Enter" && commitInterval()}
            {...anchorProps("settings.transitions.step_interval_ms")}
          />
          <Text size="xs" tone="muted">
            {t("stepIntervalDescription")}
          </Text>
        </Stack>
        <Stack gap="1.5">
          <Label htmlFor={sizeId} className="text-xs">
            {t("stepSizeLabel")}
          </Label>
          <Input
            id={sizeId}
            type="number"
            inputMode="numeric"
            min={1}
            placeholder={t("stepSizePlaceholder")}
            value={size}
            disabled={disabled}
            aria-invalid={sizeValue === undefined || undefined}
            onChange={(e) => setSizeText(e.target.value)}
            onBlur={commitSize}
            onKeyDown={(e) => e.key === "Enter" && commitSize()}
            {...anchorProps("settings.transitions.step_size")}
          />
          <Text size="xs" tone="muted">
            {t("stepSizeDescription")}
          </Text>
        </Stack>
      </Grid>
    </Stack>
  );
}

/**
 * The install-wide transition plugins switch (`plugins.transition_plugins_enabled`,
 * Settings → Advanced → Beta until settings v6). It applies to every display,
 * and says so; it sits here because this is where a plugin would be chosen.
 */
function TransitionPluginsSwitch({ boardId }: { boardId: string }) {
  const t = useTranslations("displays.transition");
  const { data: settings } = usePluginSettings();
  const mutation = useUpdatePluginSettings({
    onSuccess: () => toast.success(t("pluginsSavedToast")),
    onError: (err) => toast.error(t("pluginsSaveFailedToast", { error: err.message })),
  });
  const switchId = `transition-plugins-${boardId}`;
  const descriptionId = `${switchId}-description`;
  // Hidden until loaded, like every switch whose "off" would read as a fact.
  if (!settings) return null;
  return (
    <Flex
      align="start"
      justify="between"
      gap="4"
      className="rounded-md border p-4"
      data-testid="display-transition-plugins"
    >
      <Stack gap="1">
        <Flex align="center" gap="2">
          <Label htmlFor={switchId} className="text-sm font-medium">
            {t("pluginsLabel")}
          </Label>
          <Badge variant="outline" className="text-[10px] uppercase tracking-wide">
            {t("pluginsBadge")}
          </Badge>
        </Flex>
        <Text id={descriptionId} size="xs" tone="muted">
          {t("pluginsDescription")}
        </Text>
      </Stack>
      <Switch
        id={switchId}
        checked={settings.transition_plugins_enabled}
        disabled={mutation.isPending}
        onCheckedChange={(checked) => mutation.mutate({ transition_plugins_enabled: checked })}
        aria-describedby={descriptionId}
        {...anchorProps("settings.plugins.transition_plugins_enabled")}
      />
    </Flex>
  );
}
