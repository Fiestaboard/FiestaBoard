"use client";

/**
 * A board's settings screen rendered from its output's declaration (plan D13):
 * the `output_config` settings schema (sections, `ui:visible_when`, the core
 * widgets) and the output's actions as buttons. No plugin code runs here —
 * every output's screen is drawn this way, the Vestaboard's included.
 *
 * Actions go to the saved-board route (`POST /boards/{id}/actions/{action}`,
 * with the edited settings; `"***"` is restored server-side) when `boardId`
 * is set, else to the draft route (`POST /outputs/{id}/actions/{action}`) —
 * the add-board dialog and the setup wizard, before a board exists. An action
 * with an `input_schema` asks for its input in a dialog first, starting from
 * the settings of the same name.
 *
 * Which fields and buttons show is `ui:visible_when` over the settings and
 * the board's `facts` (`@device_type`, `@device_model`); an action a visible
 * widget runs itself (a device picker's discover, a tile grid's per-tile
 * actions) is not repeated as a button.
 *
 * A result shows its status, message and guidance; its `fields` fill the
 * settings they name (a secret one lands in a secret input, so it is never
 * shown in clear unless the user asks), and its `geometry` is handed to
 * `onGeometry` — at once for an `auto_apply` action, else on "Apply size".
 */
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  List,
  ListItem,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { AlertCircle, AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { asJSONSchema, type JSONSchema, SchemaForm, type SchemaProperty } from "@/components/plugin-settings";
import {
  BoardActionsContext,
  type BoardActionsContextValue,
  missingInputs,
  type RunOptions,
} from "@/components/plugin-settings/board-widgets";
import { BoardScreenContext } from "@/components/plugin-settings/field-context";
import { useTranslations } from "@/i18n/translations";
import type { ActionGeometry, ActionResult, OutputActionDescriptor, OutputSummary } from "@/lib/api";
import { api } from "@/lib/api";
import { type BoardFacts, isVisible } from "@/lib/visible-when";

import { localizeOutput } from "./localize-output";

const MASKED = "***";

function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);
}

function visibleProps(
  props: Record<string, SchemaProperty> | undefined,
  values: Record<string, unknown>,
  facts: BoardFacts,
): [string, SchemaProperty][] {
  const all = props ?? {};
  return Object.entries(all).filter(([, prop]) =>
    isVisible(prop["ui:visible_when"], values, all as Record<string, unknown>, facts),
  );
}

/** Actions a visible widget runs itself (a device picker's discover, a tile grid's per-tile actions). */
export function widgetActionIds(schema: JSONSchema, values: Record<string, unknown>, facts: BoardFacts): Set<string> {
  const ids = new Set<string>();
  const walk = (props: Record<string, SchemaProperty> | undefined, scope: Record<string, unknown>) => {
    for (const [, prop] of visibleProps(props, scope, facts)) {
      const widget = prop["ui:widget"];
      const options = prop["ui:options"] ?? {};
      if (widget === "device-picker") ids.add(typeof options.action === "string" ? options.action : "discover");
      if (widget === "tile-grid") {
        for (const id of options.item_actions ?? []) ids.add(id);
        if (prop.items?.properties) walk(prop.items.properties, {});
      }
      if (prop.properties) walk(prop.properties, {});
    }
  };
  walk(schema.properties, values);
  return ids;
}

/** Apply an action's result fields to the settings they fill. */
export function applyResultFields(
  values: Record<string, unknown>,
  result: ActionResult,
  schema: Record<string, unknown>,
): { values: Record<string, unknown>; filled: string[] } {
  const properties = (schema.properties ?? {}) as Record<string, { title?: string }>;
  const next = { ...values };
  const filled: string[] = [];
  for (const [name, field] of Object.entries(result.fields ?? {})) {
    const target = field.fills ?? name;
    if (!(target in properties)) continue;
    next[target] = field.value;
    filled.push(properties[target]?.title || target);
  }
  return { values: next, filled };
}

/** An action's input to start from: the settings of the same name, never a masked secret. */
function initialInput(action: OutputActionDescriptor, values: Record<string, unknown>): Record<string, unknown> {
  const declared = (action.input_schema?.properties ?? {}) as Record<string, unknown>;
  return Object.fromEntries(
    Object.keys(declared)
      .filter((name) => !isEmpty(values[name]) && values[name] !== MASKED)
      .map((name) => [name, values[name]]),
  );
}

/** Looks up `outputSettings.<key>`; `undefined` when the app carries no such message. */
function useOutputText(): (key: string) => string | undefined {
  const t = useTranslations("outputSettings");
  return useCallback(
    (key: string) => {
      const text = t(key);
      return text === `outputSettings.${key}` ? undefined : text;
    },
    [t],
  );
}

export interface PluginBoardSettingsProps {
  output: OutputSummary;
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
  /** A saved board: actions run on it. Omitted: a draft (no board yet). */
  boardId?: string;
  /** The device model a draft would be created as. */
  deviceModel?: string;
  /** The board's shape and model, read by `ui:visible_when` as `@device_type` / `@device_model`. */
  facts?: BoardFacts;
  /** The board's tile layout (devices down × across), for a `tile-grid` with `layout: "board"`. */
  layout?: { rows: number; cols: number } | null;
  /** Apply a detected size. Without it, detect-size still reports what it found. */
  onGeometry?: (geometry: ActionGeometry) => void;
  /** Every action's answer, after the screen has shown it (the wizard saves on a passing test). */
  onActionResult?: (actionId: string, result: ActionResult) => void;
  disabled?: boolean;
}

interface Asking {
  action: OutputActionDescriptor;
  initial: Record<string, unknown>;
  resolve: (input: Record<string, unknown> | null) => void;
}

export function PluginBoardSettings({
  output: declared,
  values,
  onChange,
  boardId,
  deviceModel,
  facts,
  layout,
  onGeometry,
  onActionResult,
  disabled,
}: PluginBoardSettingsProps) {
  const t = useTranslations("boardSettingsScreen");
  const text = useOutputText();
  const output = useMemo(() => localizeOutput(declared, text), [declared, text]);
  const boardFacts = useMemo<BoardFacts>(() => facts ?? {}, [facts]);
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<{
    action: OutputActionDescriptor;
    result: ActionResult;
    filled: string[];
    applied: boolean;
  } | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [asking, setAsking] = useState<Asking | null>(null);
  const schema = useMemo(() => asJSONSchema(output.settings_schema), [output.settings_schema]);
  // The latest settings, for an action that finishes after they changed.
  const latest = useRef(values);
  useEffect(() => {
    latest.current = values;
  }, [values]);

  const run = useCallback(
    async (actionId: string, input?: Record<string, unknown>, options?: RunOptions): Promise<ActionResult | null> => {
      const action = output.actions.find((a) => a.id === actionId);
      if (!action) return null;
      setRunning(actionId);
      setFailure(null);
      try {
        const response = boardId
          ? await api.runBoardAction(boardId, actionId, { input, output_config: values })
          : await api.runDraftOutputAction(output.id, actionId, {
              output_config: values,
              input,
              ...(deviceModel ? { device_model: deviceModel } : {}),
            });
        const applied =
          options?.applyFills === false
            ? { values: latest.current, filled: [] }
            : applyResultFields(latest.current, response, output.settings_schema);
        if (applied.filled.length > 0) onChange(applied.values);
        const autoApplied = !!(action.auto_apply && response.geometry && onGeometry);
        if (autoApplied) onGeometry!(response.geometry!);
        setResult({ action, result: response, filled: applied.filled, applied: autoApplied });
        onActionResult?.(actionId, response);
        return response;
      } catch (error) {
        setResult(null);
        setFailure(error instanceof Error ? error.message : t("actionFailed"));
        return null;
      } finally {
        setRunning(null);
      }
    },
    [boardId, deviceModel, onActionResult, onChange, onGeometry, output, t, values],
  );

  const requestInput = (action: OutputActionDescriptor, initial: Record<string, unknown>) =>
    new Promise<Record<string, unknown> | null>((resolve) => setAsking({ action, initial, resolve }));

  const context: BoardActionsContextValue = useMemo(
    () => ({ actions: output.actions, run, running }),
    [output.actions, run, running],
  );
  const screen = useMemo(() => ({ facts: boardFacts, layout: layout ?? null }), [boardFacts, layout]);

  const props = schema.properties as Record<string, unknown>;
  const inWidgets = widgetActionIds(schema, values, boardFacts);
  const buttons = output.actions.filter(
    (a) => !inWidgets.has(a.id) && isVisible(a.visible_when ?? undefined, values, props, boardFacts),
  );
  const missing = visibleProps(schema.properties, values, boardFacts)
    .filter(([name]) => schema.required?.includes(name) && isEmpty(values[name]))
    .map(([name, prop]) => prop.title || name);

  const onButton = async (action: OutputActionDescriptor) => {
    if (!action.input_schema) {
      void run(action.id);
      return;
    }
    const input = await requestInput(action, initialInput(action, values));
    if (input) void run(action.id, input);
  };

  return (
    <BoardScreenContext.Provider value={screen}>
      <BoardActionsContext.Provider value={context}>
        <Stack gap="4" data-testid="plugin-board-settings">
          <SchemaForm
            schema={schema}
            values={values}
            onChange={onChange}
            disabled={disabled}
            pluginId={output.builtin ? undefined : output.id}
            idPrefix={`${output.id}-${boardId ?? "draft"}-`}
          />

          {missing.length > 0 && (
            <Flex align="center" gap="1.5" data-testid="settings-missing">
              <AlertCircle className="h-4 w-4 flex-shrink-0 text-destructive" aria-hidden="true" />
              <Text as="span" size="xs">
                {t("requiredMissing", { fields: missing.join(", ") })}
              </Text>
            </Flex>
          )}

          {buttons.length > 0 && (
            <Flex gap="2" wrap role="group" aria-label={t("actionsLabel")}>
              {buttons.map((action) => (
                <Button
                  key={action.id}
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={disabled || running !== null}
                  aria-busy={running === action.id}
                  title={action.description || undefined}
                  data-testid={`action-${action.id}`}
                  onClick={() => void onButton(action)}
                >
                  {running === action.id && <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden="true" />}
                  {action.label}
                </Button>
              ))}
            </Flex>
          )}

          <Box aria-live="polite">
            {failure && (
              <Alert variant="destructive" data-testid="action-failure">
                <XCircle className="h-4 w-4" aria-hidden="true" />
                <AlertTitle>{t("resultError")}</AlertTitle>
                <AlertDescription>{failure}</AlertDescription>
              </Alert>
            )}
            {result && <ActionResultPanel {...result} onGeometry={onGeometry} />}
          </Box>

          <Dialog
            open={asking !== null}
            onOpenChange={(open) => {
              if (!open && asking) {
                asking.resolve(null);
                setAsking(null);
              }
            }}
          >
            {asking && (
              <ActionInputDialog
                key={asking.action.id}
                action={asking.action}
                initial={asking.initial}
                onRun={(input) => {
                  asking.resolve(input);
                  setAsking(null);
                }}
              />
            )}
          </Dialog>
        </Stack>
      </BoardActionsContext.Provider>
    </BoardScreenContext.Provider>
  );
}

function ActionInputDialog({
  action,
  initial,
  onRun,
}: {
  action: OutputActionDescriptor;
  initial: Record<string, unknown>;
  onRun: (input: Record<string, unknown>) => void;
}) {
  const t = useTranslations("boardSettingsScreen");
  const tc = useTranslations("common");
  const [input, setInput] = useState<Record<string, unknown>>(initial);
  const schema = useMemo(() => asJSONSchema(action.input_schema), [action.input_schema]);
  const missing = missingInputs(action, input).length > 0;

  return (
    <DialogContent>
      <Box
        as="form"
        onSubmit={(event) => {
          event.preventDefault();
          // The dialog is portalled out of the DOM tree but not out of React's:
          // without this, its submit bubbles into any <form> hosting the screen
          // (the Add Board dialog) and submits that too.
          event.stopPropagation();
          if (!missing) onRun(input);
        }}
      >
        <DialogHeader>
          <DialogTitle>{action.label}</DialogTitle>
          <DialogDescription>{action.description || t("actionInputDescription")}</DialogDescription>
        </DialogHeader>
        <SchemaForm
          schema={schema}
          values={input}
          onChange={setInput}
          className="py-4"
          idPrefix={`action-${action.id}-`}
        />
        <DialogFooter>
          <Button type="submit" disabled={missing}>
            {tc("next")}
          </Button>
        </DialogFooter>
      </Box>
    </DialogContent>
  );
}

function ActionResultPanel({
  action,
  result,
  filled,
  applied,
  onGeometry,
}: {
  action: OutputActionDescriptor;
  result: ActionResult;
  filled: string[];
  applied: boolean;
  onGeometry?: (geometry: ActionGeometry) => void;
}) {
  const t = useTranslations("boardSettingsScreen");
  const variant = result.status === "ok" ? "success" : result.status === "warning" ? "warning" : "destructive";
  const Icon = result.status === "ok" ? CheckCircle2 : result.status === "warning" ? AlertTriangle : XCircle;
  const title =
    result.status === "ok" ? t("resultOk") : result.status === "warning" ? t("resultWarning") : t("resultError");

  return (
    <Alert variant={variant} data-testid="action-result" data-status={result.status}>
      <Icon className="h-4 w-4" aria-hidden="true" />
      <AlertTitle>
        {title} · {action.label}
      </AlertTitle>
      <AlertDescription>
        <Stack gap="2">
          {result.message && <Text size="sm">{result.message}</Text>}
          {result.guidance.length > 0 && (
            <Stack gap="1">
              <Text size="xs" weight="medium">
                {t("guidanceLabel")}
              </Text>
              <List>
                {result.guidance.map((line) => (
                  <ListItem key={line}>{line}</ListItem>
                ))}
              </List>
            </Stack>
          )}
          {filled.length > 0 && <Text size="xs">{t("fieldsFilled", { fields: filled.join(", ") })}</Text>}
          {result.geometry && (
            <Flex align="center" gap="2" wrap>
              <Text size="xs">
                {applied
                  ? t("geometryApplied", { rows: result.geometry.rows, cols: result.geometry.cols })
                  : t("geometryDetected", { rows: result.geometry.rows, cols: result.geometry.cols })}
              </Text>
              {onGeometry && !applied && (
                <Button type="button" size="sm" variant="outline" onClick={() => onGeometry(result.geometry!)}>
                  {t("applyGeometry")}
                </Button>
              )}
            </Flex>
          )}
          {result.devices && result.devices.length === 0 && <Text size="xs">{t("noDevicesFound")}</Text>}
          {result.devices && result.devices.length > 0 && (
            <List>
              {result.devices.map((device) => (
                <ListItem key={`${device.ip}:${device.port}`}>
                  {device.hostname || device.label || device.ip} ({device.ip}:{device.port})
                </ListItem>
              ))}
            </List>
          )}
        </Stack>
      </AlertDescription>
    </Alert>
  );
}
