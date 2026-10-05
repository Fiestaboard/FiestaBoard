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
 * A scan (`discover`, an action declaring `hint_host`, a device picker's)
 * carries `hint_host`, the private IPv4 address the page was opened at
 * (`@/lib/network-hint`): in Docker bridge mode it is how the output learns
 * which network to search. It is filled in, never asked for.
 *
 * A result shows its status, message and guidance right where the action
 * was run — under its button, or in the device picker that ran it — never
 * in one box for the whole form; a request that failed outright shows there
 * too. A required setting still empty says so on its own field. A result's
 * `fields` fill the settings they name (a secret one lands in a secret input, so it is never
 * shown in clear unless the user asks), and its `geometry` is handed to
 * `onGeometry` — at once for an `auto_apply` action, else on "Apply size".
 */
import {
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Stack,
} from "@fiestaboard/ui";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { asJSONSchema, type JSONSchema, SchemaForm, type SchemaProperty } from "@/components/plugin-settings";
import { ActionFeedback, type ActionFeedbackEntry } from "@/components/plugin-settings/action-feedback";
import {
  BoardActionsContext,
  type BoardActionsContextValue,
  missingInputs,
  pickerFallbacks,
  type RunOptions,
} from "@/components/plugin-settings/board-widgets";
import { BoardScreenContext } from "@/components/plugin-settings/field-context";
import { useTranslations } from "@/i18n/translations";
import type { ActionGeometry, ActionResult, OutputActionDescriptor, OutputSummary } from "@/lib/api";
import { api } from "@/lib/api";
import { browserHostname, HINT_HOST, lanHintHost, withNetworkHint } from "@/lib/network-hint";
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

/**
 * Actions a visible widget runs itself: a device picker's discover and the
 * lookups it offers when that finds nothing, a tile grid's per-tile actions.
 */
export function widgetActionIds(
  schema: JSONSchema,
  values: Record<string, unknown>,
  facts: BoardFacts,
  actions: OutputActionDescriptor[] = [],
): Set<string> {
  const ids = new Set<string>();
  const walk = (props: Record<string, SchemaProperty> | undefined, scope: Record<string, unknown>) => {
    for (const [key, prop] of visibleProps(props, scope, facts)) {
      const widget = prop["ui:widget"];
      const options = prop["ui:options"] ?? {};
      if (widget === "device-picker") {
        const action = typeof options.action === "string" ? options.action : "discover";
        ids.add(action);
        for (const alt of pickerFallbacks(actions, action, key)) ids.add(alt.id);
      }
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

/** The inputs an action asks the user for: all it declares but `hint_host`, which is filled in. */
function askedInputs(action: OutputActionDescriptor): Record<string, unknown> {
  const declared = (action.input_schema?.properties ?? {}) as Record<string, unknown>;
  return Object.fromEntries(Object.entries(declared).filter(([name]) => name !== HINT_HOST));
}

/** An action's input to start from: the settings of the same name, never a masked secret. */
function initialInput(action: OutputActionDescriptor, values: Record<string, unknown>): Record<string, unknown> {
  const declared = askedInputs(action);
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
  // Each action's last answer, kept by where it was run (its button, or the
  // widget that ran it) so it shows there.
  const [feedback, setFeedback] = useState<Record<string, ActionFeedbackEntry>>({});
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
      const sent = withNetworkHint(action, input, lanHintHost(browserHostname()), options?.networkHint);
      const origin = options?.origin ?? actionId;
      const answer = (entry: Omit<ActionFeedbackEntry, "action">) =>
        setFeedback((current) => ({ ...current, [origin]: { action, ...entry } }));
      setRunning(actionId);
      setFeedback((current) => {
        const rest = { ...current };
        delete rest[origin];
        return rest;
      });
      try {
        const response = boardId
          ? await api.runBoardAction(boardId, actionId, { input: sent, output_config: values })
          : await api.runDraftOutputAction(output.id, actionId, {
              output_config: values,
              input: sent,
              ...(deviceModel ? { device_model: deviceModel } : {}),
            });
        const applied =
          options?.applyFills === false
            ? { values: latest.current, filled: [] }
            : applyResultFields(latest.current, response, output.settings_schema);
        if (applied.filled.length > 0) onChange(applied.values);
        const autoApplied = !!(action.auto_apply && response.geometry && onGeometry);
        if (autoApplied) onGeometry!(response.geometry!);
        answer({ result: response, error: null, filled: applied.filled, applied: autoApplied });
        onActionResult?.(actionId, response);
        return response;
      } catch (error) {
        answer({
          result: null,
          error: error instanceof Error ? error.message : t("actionFailed"),
          filled: [],
          applied: false,
        });
        return null;
      } finally {
        setRunning(null);
      }
    },
    [boardId, deviceModel, onActionResult, onChange, onGeometry, output, t, values],
  );

  /** Run an action from a button, asking for its input first when it declares any. */
  const start = useCallback(
    async (actionId: string, origin?: string) => {
      const action = output.actions.find((a) => a.id === actionId);
      if (!action) return;
      if (Object.keys(askedInputs(action)).length === 0) {
        void run(action.id, undefined, { origin });
        return;
      }
      const input = await new Promise<Record<string, unknown> | null>((resolve) =>
        setAsking({ action, initial: initialInput(action, latest.current), resolve }),
      );
      if (input) void run(action.id, input, { origin });
    },
    [output.actions, run],
  );

  const context: BoardActionsContextValue = useMemo(
    () => ({
      actions: output.actions,
      run,
      running,
      feedback,
      start: (actionId: string, origin: string) => void start(actionId, origin),
      deviceName: output.name,
      onGeometry,
    }),
    [output.actions, output.name, run, running, feedback, start, onGeometry],
  );
  const screen = useMemo(() => ({ facts: boardFacts, layout: layout ?? null }), [boardFacts, layout]);

  const props = schema.properties as Record<string, unknown>;
  const inWidgets = widgetActionIds(schema, values, boardFacts, output.actions);
  const buttons = output.actions.filter(
    (a) => !inWidgets.has(a.id) && isVisible(a.visible_when ?? undefined, values, props, boardFacts),
  );

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
            requiredHints
          />

          {buttons.length > 0 && (
            <Stack gap="3" role="group" aria-label={t("actionsLabel")}>
              {buttons.map((action) => (
                <Stack key={action.id} gap="2" data-testid={`action-item-${action.id}`}>
                  <Box>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={disabled || (running !== null && running !== action.id)}
                      loading={running === action.id}
                      title={action.description || undefined}
                      data-testid={`action-${action.id}`}
                      onClick={() => void start(action.id)}
                    >
                      {action.label}
                    </Button>
                  </Box>
                  <Box aria-live="polite" data-testid={`action-feedback-${action.id}`}>
                    {feedback[action.id] && <ActionFeedback entry={feedback[action.id]} onGeometry={onGeometry} />}
                  </Box>
                </Stack>
              ))}
            </Stack>
          )}

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
  const schema = useMemo(() => asJSONSchema({ ...action.input_schema, properties: askedInputs(action) }), [action]);
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
