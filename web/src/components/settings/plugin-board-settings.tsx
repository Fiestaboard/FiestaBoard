"use client";

/**
 * A board's settings screen rendered from its output's declaration (plan D13):
 * the `output_config` settings schema (sections, `ui:visible_when`, the core
 * widgets) and the output's actions as buttons. No plugin code runs here.
 *
 * Actions go to the saved-board route (`POST /boards/{id}/actions/{action}`,
 * with the edited settings; `"***"` is restored server-side) when `boardId`
 * is set, else to the draft route (`POST /outputs/{id}/actions/{action}`) —
 * the add-board dialog and the setup wizard, before a board exists. An action
 * with an `input_schema` asks for its input in a dialog first.
 *
 * A result shows its status, message and guidance; its `fields` fill the
 * settings they name (a secret one lands in a secret input, so it is never
 * shown in clear unless the user asks), and its `geometry` is handed to
 * `onGeometry` to apply.
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
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { asJSONSchema, SchemaForm } from "@/components/plugin-settings";
import { BoardActionsContext, type BoardActionsContextValue } from "@/components/plugin-settings/board-widgets";
import { useTranslations } from "@/i18n/translations";
import type { ActionGeometry, ActionResult, OutputActionDescriptor, OutputSummary } from "@/lib/api";
import { api } from "@/lib/api";

/** Actions rendered inside a widget (discover by a device picker, identify per tile) rather than as buttons. */
function widgetActionIds(schema: Record<string, unknown>): Set<string> {
  const ids = new Set<string>();
  const walk = (props: unknown) => {
    if (!props || typeof props !== "object") return;
    for (const prop of Object.values(props as Record<string, Record<string, unknown>>)) {
      const widget = prop?.["ui:widget"];
      const options = (prop?.["ui:options"] ?? {}) as Record<string, unknown>;
      if (widget === "device-picker") ids.add(typeof options.action === "string" ? options.action : "discover");
      if (widget === "tile-grid") ids.add("identify");
      walk(prop?.properties);
      walk((prop?.items as Record<string, unknown> | undefined)?.properties);
    }
  };
  walk(schema.properties);
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

export interface PluginBoardSettingsProps {
  output: OutputSummary;
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
  /** A saved board: actions run on it. Omitted: a draft (no board yet). */
  boardId?: string;
  /** The device model a draft would be created as. */
  deviceModel?: string;
  /** Apply a detected size. Without it, detect-size still reports what it found. */
  onGeometry?: (geometry: ActionGeometry) => void;
  disabled?: boolean;
}

export function PluginBoardSettings({
  output,
  values,
  onChange,
  boardId,
  deviceModel,
  onGeometry,
  disabled,
}: PluginBoardSettingsProps) {
  const t = useTranslations("boardSettingsScreen");
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<{
    action: OutputActionDescriptor;
    result: ActionResult;
    filled: string[];
  } | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [asking, setAsking] = useState<OutputActionDescriptor | null>(null);
  const schema = useMemo(() => asJSONSchema(output.settings_schema), [output.settings_schema]);

  const run = useCallback(
    async (actionId: string, input?: Record<string, unknown>): Promise<ActionResult | null> => {
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
        const applied = applyResultFields(values, response, output.settings_schema);
        if (applied.filled.length > 0) onChange(applied.values);
        setResult({ action, result: response, filled: applied.filled });
        return response;
      } catch (error) {
        setResult(null);
        setFailure(error instanceof Error ? error.message : t("actionFailed"));
        return null;
      } finally {
        setRunning(null);
      }
    },
    [boardId, deviceModel, onChange, output, t, values],
  );

  const context: BoardActionsContextValue = useMemo(
    () => ({ actions: output.actions, run, running }),
    [output.actions, run, running],
  );

  const inWidgets = useMemo(() => widgetActionIds(output.settings_schema), [output.settings_schema]);
  const buttons = output.actions.filter((a) => !inWidgets.has(a.id));

  return (
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
                onClick={() => (action.input_schema ? setAsking(action) : void run(action.id))}
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

        <Dialog open={asking !== null} onOpenChange={(open) => !open && setAsking(null)}>
          {asking && (
            <ActionInputDialog
              key={asking.id}
              action={asking}
              onRun={(input) => {
                setAsking(null);
                void run(asking.id, input);
              }}
            />
          )}
        </Dialog>
      </Stack>
    </BoardActionsContext.Provider>
  );
}

function ActionInputDialog({
  action,
  onRun,
}: {
  action: OutputActionDescriptor;
  onRun: (input: Record<string, unknown>) => void;
}) {
  const t = useTranslations("boardSettingsScreen");
  const tc = useTranslations("common");
  const [input, setInput] = useState<Record<string, unknown>>({});
  const schema = useMemo(() => asJSONSchema(action.input_schema), [action.input_schema]);
  const missing = (schema.required ?? []).some((name) => input[name] === undefined || input[name] === "");

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
  onGeometry,
}: {
  action: OutputActionDescriptor;
  result: ActionResult;
  filled: string[];
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
              <Text size="xs">{t("geometryDetected", { rows: result.geometry.rows, cols: result.geometry.cols })}</Text>
              {onGeometry && (
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
