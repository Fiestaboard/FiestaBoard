"use client";

/**
 * The core board-setup widgets of the settings contract (plan D13) — a
 * closed set, built from @fiestaboard/ui primitives; a plugin declares them
 * in its schema and never ships UI code:
 *
 * - `mode-cards`: a string `enum` as a radiogroup of cards
 *   (`ui:options.cards: [{value, title, description}]`).
 * - `device-picker`: a text field plus a button named by the output's
 *   discover action (`ui:options.action`). While it searches it says which
 *   network; what it found shows right under the field as a pick-list (the
 *   only one found is picked for you); picking one fills the field
 *   (`value_key`, read from the device's `fields` first) and the device's
 *   other `fields` this form declares. Nothing found says so, with the way
 *   on: type the address, the output's other lookups (an action whose
 *   `result_fields` fill this field), search again. "Enter address
 *   manually" is always there.
 *   The scan carries the page's private IPv4 address as `hint_host`, and,
 *   when the action declares a `subnet` input, a network the user may type.
 * - `tile-grid`: an array of `{row, col, ...}` items as a rows × cols grid
 *   of slots (`ui:options.rows_field` / `cols_field`, or `layout: "board"`
 *   for the board's own tile layout). Each slot opens a dialog with the
 *   item's other fields and the `ui:options.item_actions` run on that one
 *   tile (their input taken from it, their result filled into it, the
 *   verdict a toast); a filled tile can move to (or swap with) another slot;
 *   `identify`, when the output declares it, also identifies every tile at
 *   once; repeated `ui:options.unique_fields` values are flagged, and a
 *   device-picker in a tile's dialog marks a found device another tile
 *   already uses.
 *
 * Actions come from {@link BoardActionsContext}, which the board settings
 * screen provides; without it the action buttons are not rendered.
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
  Flex,
  Grid,
  Input,
  Label,
  List,
  ListItem,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
  ToggleCard,
  ToggleCardGroup,
} from "@fiestaboard/ui";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Pencil,
  Plus,
  RotateCw,
  ScanSearch,
  Search,
  SearchX,
  Trash2,
} from "lucide-react";
import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import type { ActionGeometry, ActionResult, DiscoveredDevice, OutputActionDescriptor } from "@/lib/api";
import { browserHostname, declaresInput, lanHintHost, SUBNET } from "@/lib/network-hint";

import { ActionFeedback, type ActionFeedbackEntry } from "./action-feedback";
import { useFieldScope } from "./field-context";

/** How a widget runs an action. */
export interface RunOptions {
  /**
   * Fill the result's `fields` into the screen's settings (default). A tile
   * action passes `false`: its fills belong to the tile, not the board.
   */
  applyFills?: boolean;
  /**
   * A device picker's scan: send `hint_host` (the page's private IPv4
   * address) whatever the action's id. `discover` and an action declaring
   * `hint_host` get it without asking.
   */
  networkHint?: boolean;
  /**
   * Where the answer is shown: it is kept under this key in
   * {@link BoardActionsContextValue.feedback}. Defaults to the action's id
   * (its button's own spot).
   */
  origin?: string;
}

/** What the board settings screen lends its widgets: the declared actions and a runner. */
export interface BoardActionsContextValue {
  actions: OutputActionDescriptor[];
  /** Runs one action (saved or draft route, as the screen decides); `null` when it threw. */
  run: (actionId: string, input?: Record<string, unknown>, options?: RunOptions) => Promise<ActionResult | null>;
  /** The action in flight, if any. */
  running: string | null;
  /** Each action's last answer, by where it was run ({@link RunOptions.origin}). */
  feedback?: Record<string, ActionFeedbackEntry>;
  /** Run an action from a widget's button — asking for its input first when it declares any — answering at *origin*. */
  start?: (actionId: string, origin: string) => void;
  /** What the output drives, for a picker's "No Divoom Pixoo found". */
  deviceName?: string;
  /** Apply a size an action detected. */
  onGeometry?: (geometry: ActionGeometry) => void;
}

export const BoardActionsContext = createContext<BoardActionsContextValue | null>(null);

export function useBoardActions(): BoardActionsContextValue | null {
  return useContext(BoardActionsContext);
}

/**
 * Inside a tile's dialog: the slot number of ANOTHER tile that already uses
 * a value (its `unique_fields` value — a Note's address), so a device picker
 * can say a found device is taken.
 */
export const TileValueInUseContext = createContext<((value: string) => number | null) | null>(null);

/** Toast an action's verdict: its label, and its message when it has one. */
export function toastActionResult(action: OutputActionDescriptor, result: ActionResult | null, failed: string) {
  if (result === null) {
    toast.error(action.label, { description: failed });
    return;
  }
  const options = result.message ? { description: result.message } : undefined;
  if (result.status === "ok") toast.success(action.label, options);
  else if (result.status === "warning") toast.warning(action.label, options);
  else toast.error(action.label, options);
}

const MASKED = "***";

function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);
}

/** The required inputs of *action* that *input* leaves empty. */
export function missingInputs(action: OutputActionDescriptor, input: Record<string, unknown>): string[] {
  const required = (action.input_schema?.required ?? []) as unknown[];
  return required.filter((name): name is string => typeof name === "string" && isEmpty(input[name]));
}

interface Card {
  value: string;
  title?: string;
  description?: string;
}

interface ModeCardsFieldProps {
  name: string;
  label: string;
  options: unknown[];
  cards?: Card[];
  enumNames?: string[];
  value: unknown;
  defaultValue: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
}

export function ModeCardsField({
  name,
  label,
  options,
  cards,
  enumNames,
  value,
  defaultValue,
  onChange,
  disabled,
}: ModeCardsFieldProps) {
  const values = options.map((o) => String(o));
  const current = value !== undefined && value !== null ? String(value) : String(defaultValue ?? values[0] ?? "");
  return (
    <ToggleCardGroup
      id={name}
      columns={values.length >= 3 ? "3" : values.length === 2 ? "2" : "1"}
      size="sm"
      value={current}
      onValueChange={(next) => onChange(options[values.indexOf(next)] ?? next)}
      disabled={disabled}
      aria-label={label}
    >
      {values.map((option, index) => {
        const card = cards?.find((c) => String(c.value) === option);
        return (
          <ToggleCard
            key={option}
            value={option}
            title={card?.title ?? enumNames?.[index] ?? option}
            description={card?.description}
          />
        );
      })}
    </ToggleCardGroup>
  );
}

interface DevicePickerFieldProps {
  name: string;
  label: string;
  value: unknown;
  /** Commits the address, with the found device's other settings as siblings. */
  onChange: (value: unknown, siblings?: Record<string, unknown>) => void;
  placeholder?: string;
  action?: string;
  valueKey?: string;
  labelKey?: string;
  /** The setting this picker fills: an action whose result fills it is offered when a search finds nothing. */
  field?: string;
  /** Ids of the field's own hints (its "Required" line), read with the address input. */
  describedBy?: string;
  disabled?: boolean;
  required?: boolean;
}

/** A device's *key*: what the output reported under `fields` first, then the core keys. */
function deviceText(device: DiscoveredDevice, key: string): string {
  const raw = device.fields?.[key] ?? (device as unknown as Record<string, unknown>)[key];
  return raw === undefined || raw === null ? "" : String(raw);
}

/** The found device's settings that this form also declares: what picking it fills beside the address. */
function deviceSiblings(device: DiscoveredDevice, declared: Record<string, string>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(device.fields ?? {}).filter(([key]) => key in declared));
}

/**
 * The network a search covers, as a person reads it: the one they typed,
 * else the page's own /24 (`192.168.0.x`), else `null` (not known here —
 * the output searches the network it is on).
 */
export function searchedNetwork(typed: string, hint: string | null): string | null {
  if (typed) return typed;
  if (!hint) return null;
  return `${hint.split(".").slice(0, 3).join(".")}.x`;
}

/**
 * The other ways to fill a picker's setting, offered when its search finds
 * nothing: every other declared action whose `result_fields` fill that
 * setting (a Pixoo's cloud lookup fills `host`).
 */
export function pickerFallbacks(
  actions: OutputActionDescriptor[],
  pickerAction: string,
  field: string | undefined,
): OutputActionDescriptor[] {
  if (!field) return [];
  return actions.filter(
    (a) =>
      a.id !== pickerAction &&
      Object.entries(a.result_fields ?? {}).some(([name, declared]) => (declared?.fills ?? name) === field),
  );
}

export function DevicePickerField({
  name,
  label,
  value,
  onChange,
  placeholder,
  action = "discover",
  valueKey = "ip",
  labelKey = "hostname",
  field,
  describedBy,
  disabled,
  required,
}: DevicePickerFieldProps) {
  const t = useTranslations("boardSettingsScreen");
  const actions = useBoardActions();
  const inUse = useContext(TileValueInUseContext);
  const { titles } = useFieldScope();
  const [devices, setDevices] = useState<DiscoveredDevice[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [network, setNetwork] = useState<string | null>(null);
  const [autoPicked, setAutoPicked] = useState<string | null>(null);
  const [subnet, setSubnet] = useState("");
  // The one device a search found, picked once the result has rendered — so
  // the pick lands on the settings as they are then, not as they were when
  // the search began.
  const pending = useRef<DiscoveredDevice | null>(null);
  const declared = actions?.actions.find((a) => a.id === action);
  const canScan = declared !== undefined;
  const asksSubnet = declared !== undefined && declaresInput(declared, SUBNET);
  const subnetProp = asksSubnet
    ? ((declared.input_schema?.properties as Record<string, { title?: string }>)[SUBNET] ?? {})
    : null;
  const origin = `picker:${name}`;
  const altOrigin = `${origin}:alt`;
  const entry = actions?.feedback?.[origin];
  const altEntry = actions?.feedback?.[altOrigin];
  const fallbacks = actions ? pickerFallbacks(actions.actions, action, field) : [];
  const busy = actions?.running != null;
  const deviceName = actions?.deviceName || label;

  useEffect(() => {
    const device = pending.current;
    if (!device) return;
    pending.current = null;
    onChange(deviceText(device, valueKey), deviceSiblings(device, titles));
  }, [devices, onChange, titles, valueKey]);

  const focusAddress = () => document.getElementById(name)?.focus();

  const scan = async () => {
    if (!actions) return;
    const typed = subnet.trim();
    setNetwork(searchedNetwork(asksSubnet ? typed : "", lanHintHost(browserHostname())));
    setSearching(true);
    setAutoPicked(null);
    try {
      const result = await actions.run(action, asksSubnet && typed ? { [SUBNET]: typed } : undefined, {
        networkHint: true,
        origin,
      });
      const found = result?.devices ?? [];
      if (result !== null && found.length === 1 && (inUse?.(deviceText(found[0], valueKey)) ?? null) === null) {
        pending.current = found[0];
        setAutoPicked(deviceText(found[0], labelKey) || found[0].label || deviceText(found[0], valueKey));
      }
      setDevices(result === null ? null : found);
    } finally {
      setSearching(false);
    }
  };

  const searchAgain = (
    <Button type="button" variant="ghost" size="sm" onClick={() => void scan()} disabled={disabled || busy}>
      <RotateCw className="mr-1 h-4 w-4" aria-hidden="true" />
      {t("searchAgain")}
    </Button>
  );
  const enterManually = (variant: "link" | "secondary") => (
    <Button
      type="button"
      variant={variant}
      size="sm"
      className={variant === "link" ? "h-auto self-start px-0" : undefined}
      onClick={focusAddress}
      disabled={disabled}
    >
      <Pencil className="mr-1 h-4 w-4" aria-hidden="true" />
      {t("enterManually")}
    </Button>
  );
  /** What to do when the search found nothing or could not run. */
  const nextSteps = (
    <Stack gap="2">
      <Flex gap="2" wrap>
        {enterManually("secondary")}
        {fallbacks.map((alt) => (
          <Button
            key={alt.id}
            type="button"
            variant="outline"
            size="sm"
            title={alt.description || undefined}
            loading={actions?.running === alt.id}
            disabled={disabled || (busy && actions?.running !== alt.id)}
            onClick={() => actions?.start?.(alt.id, altOrigin)}
          >
            {alt.label}
          </Button>
        ))}
        {searchAgain}
      </Flex>
      <Box aria-live="polite">{altEntry && <ActionFeedback entry={altEntry} onGeometry={actions?.onGeometry} />}</Box>
    </Stack>
  );

  const searched = !searching && entry !== undefined && (devices !== null || entry.result === null);
  const failed = searched && entry.result === null;
  const empty = searched && !failed && devices !== null && devices.length === 0;
  const found = searched && !failed && devices !== null && devices.length > 0;

  return (
    <Stack gap="2" data-testid="device-picker">
      <Flex gap="2">
        <Input
          id={name}
          type="text"
          value={String(value ?? "")}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          required={required}
          aria-describedby={describedBy}
          className="flex-1"
        />
        {canScan && (
          <Button
            type="button"
            variant="secondary"
            onClick={() => void scan()}
            loading={searching}
            disabled={disabled || (busy && !searching)}
          >
            <Search className="mr-1 h-4 w-4" aria-hidden="true" />
            {declared.label}
          </Button>
        )}
      </Flex>

      {canScan && (
        <Box aria-live="polite" data-testid="device-picker-status">
          {searching && (
            <Flex align="center" gap="2">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden="true" />
              <Text as="span" size="sm" tone="muted">
                {network ? t("searchingNetwork", { network }) : t("searchingYourNetwork")}
              </Text>
            </Flex>
          )}
          {failed && (
            <Stack gap="2">
              <ActionFeedback entry={entry} onGeometry={actions?.onGeometry} />
              {nextSteps}
            </Stack>
          )}
          {empty && (
            <Stack gap="2" className="rounded-lg border border-dashed p-3" data-testid="device-picker-empty">
              <Flex align="start" gap="2">
                <SearchX className="mt-0.5 h-4 w-4 flex-shrink-0 text-warning" aria-hidden="true" />
                <Text size="sm" weight="medium">
                  {entry.result?.message ||
                    (network
                      ? t("noDeviceFoundOn", { device: deviceName, network })
                      : t("noDeviceFoundHere", { device: deviceName }))}
                </Text>
              </Flex>
              {entry.result && entry.result.guidance.length > 0 && (
                <List>
                  {entry.result.guidance.map((line) => (
                    <ListItem key={line}>
                      <Text as="span" size="xs">
                        {line}
                      </Text>
                    </ListItem>
                  ))}
                </List>
              )}
              {nextSteps}
            </Stack>
          )}
          {found && (
            <Stack gap="1">
              <Flex align="start" gap="2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-success" aria-hidden="true" />
                <Text size="sm">
                  {autoPicked
                    ? t("foundOneSelected", { device: autoPicked })
                    : t("foundDevices", { count: devices.length })}
                </Text>
              </Flex>
              {entry.result?.message && (
                <Text size="xs" tone="muted">
                  {entry.result.message}
                </Text>
              )}
            </Stack>
          )}
        </Box>
      )}

      {found && (
        <>
          <ToggleCardGroup
            size="sm"
            columns="1"
            value={String(value ?? "")}
            onValueChange={(next) => {
              const picked = devices.find((device) => deviceText(device, valueKey) === next);
              onChange(next, picked ? deviceSiblings(picked, titles) : undefined);
            }}
            aria-label={t("devicesFoundLabel", { field: label })}
          >
            {devices.map((device) => {
              const deviceValue = deviceText(device, valueKey);
              const usedBy = inUse?.(deviceValue) ?? null;
              return (
                <ToggleCard
                  key={`${deviceValue}:${device.port}`}
                  value={deviceValue}
                  title={deviceText(device, labelKey) || device.label || deviceValue}
                  description={
                    usedBy !== null
                      ? `${device.ip}:${device.port} · ${t("deviceInUse", { position: usedBy })}`
                      : `${device.ip}:${device.port}`
                  }
                />
              );
            })}
          </ToggleCardGroup>
          <Flex gap="2" wrap>
            {enterManually("link")}
            {searchAgain}
          </Flex>
        </>
      )}

      {!searched && !searching && enterManually("link")}

      {canScan && subnetProp && (
        <Stack gap="1">
          <Label htmlFor={`${name}-subnet`}>{subnetProp.title || t("subnetLabel")}</Label>
          <Input
            id={`${name}-subnet`}
            type="text"
            value={subnet}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSubnet(e.target.value)}
            placeholder="192.168.1.0/24"
            disabled={disabled || searching}
          />
        </Stack>
      )}
    </Stack>
  );
}

// --- tile-grid -----------------------------------------------------------------------------------

type Tile = Record<string, unknown> & { row: number; col: number };

interface ItemProperty {
  title?: string;
  default?: unknown;
}

interface TileGridFieldProps {
  name: string;
  label: string;
  value: unknown;
  onChange: (value: unknown) => void;
  rows: number;
  cols: number;
  /** The item's own fields (everything but row/col). */
  itemProperties: Record<string, ItemProperty>;
  /** Item fields a tile needs before it counts as assigned (and can be saved). */
  itemRequired?: string[];
  /** Declared actions run on one tile from its dialog. */
  itemActions?: string[];
  /** Item fields that together should not repeat across tiles. */
  uniqueFields?: string[];
  /** Renders the form for a tile's own fields. */
  renderTileFields: (
    tile: Record<string, unknown>,
    onTileChange: (tile: Record<string, unknown>) => void,
  ) => React.ReactNode;
  /** Renders the form for the inputs a tile action needs beyond the tile's own fields. */
  renderActionInput: (
    action: OutputActionDescriptor,
    schema: Record<string, unknown>,
    input: Record<string, unknown>,
    onInputChange: (input: Record<string, unknown>) => void,
  ) => React.ReactNode;
  disabled?: boolean;
}

function asTiles(value: unknown): Tile[] {
  return Array.isArray(value)
    ? value.filter(
        (t): t is Tile =>
          !!t && typeof t === "object" && typeof (t as Tile).row === "number" && typeof (t as Tile).col === "number",
      )
    : [];
}

/** Reading-order slot number. */
function slotNumber(row: number, col: number, cols: number): number {
  return row * cols + col + 1;
}

function tileReady(tile: Record<string, unknown>, required: string[]): boolean {
  return required.every((name) => !isEmpty(tile[name]));
}

/**
 * The input an action run on one tile sends: the tile's values for the keys
 * the action's `input_schema` declares. A saved tile reads its secrets back
 * masked (`"***"`): when a declared key is masked, the tile is named by its
 * position alone, so the server acts on the stored tile instead of being
 * handed three asterisks as a credential.
 */
export function tileActionInput(action: OutputActionDescriptor, tile: Tile): Record<string, unknown> {
  const declared = (action.input_schema?.properties ?? null) as Record<string, unknown> | null;
  if (!declared) return {};
  const masked = Object.entries(tile).some(([key, v]) => key in declared && v === MASKED);
  const source: Record<string, unknown> = masked ? { row: tile.row, col: tile.col } : tile;
  return Object.fromEntries(Object.entries(source).filter(([key, v]) => key in declared && !isEmpty(v)));
}

export function TileGridField({
  name,
  label,
  value,
  onChange,
  rows,
  cols,
  itemProperties,
  itemRequired = [],
  itemActions = [],
  uniqueFields = [],
  renderTileFields,
  renderActionInput,
  disabled,
}: TileGridFieldProps) {
  const t = useTranslations("boardSettingsScreen");
  const actions = useBoardActions();
  const tiles = useMemo(() => asTiles(value), [value]);
  const [editing, setEditing] = useState<{ row: number; col: number } | null>(null);
  const safeRows = Math.max(1, Math.min(rows, 12));
  const safeCols = Math.max(1, Math.min(cols, 12));
  const total = safeRows * safeCols;

  // Out-of-range tiles are kept (shrinking and re-growing never loses a
  // tile's settings) but are neither shown nor counted.
  const inRange = useMemo(
    () => tiles.filter((tile) => tile.row < safeRows && tile.col < safeCols),
    [tiles, safeRows, safeCols],
  );
  const at = (row: number, col: number) => inRange.find((tile) => tile.row === row && tile.col === col);
  const assigned = inRange.filter((tile) => tile.enabled !== false && tileReady(tile, itemRequired)).length;

  const summaryField = uniqueFields[0];
  const summary = (tile: Tile | undefined) =>
    tile && summaryField && !isEmpty(tile[summaryField]) ? String(tile[summaryField]) : "";

  const duplicates = useMemo(() => {
    if (uniqueFields.length === 0) return [];
    const seen = new Map<string, number>();
    for (const tile of inRange) {
      if (isEmpty(tile[uniqueFields[0]])) continue;
      const key = uniqueFields.map((f) => String(tile[f] ?? itemProperties[f]?.default ?? "")).join(":");
      seen.set(key, (seen.get(key) ?? 0) + 1);
    }
    return [...seen.entries()].filter(([, count]) => count > 1).map(([key]) => key);
  }, [inRange, uniqueFields, itemProperties]);

  const identify = actions?.actions.find((a) => a.id === "identify");
  const identifyAllOrigin = `tile-grid:${name}:identify-all`;
  const identifyAll = (() => {
    const target = (identify?.input_schema?.properties as Record<string, { enum?: unknown[] }> | undefined)?.target;
    return Array.isArray(target?.enum) && target.enum.includes("all");
  })();

  const replace = (next: Tile | null, at: { row: number; col: number }) => {
    const others = tiles.filter((x) => !(x.row === at.row && x.col === at.col));
    onChange(next ? [...others, next] : others);
    setEditing(null);
    toast.success(next ? t("tileSaved") : t("tileRemoved"));
  };

  /** The slot of another in-range tile whose first unique field is *value*. */
  const inUseBy = (except: { row: number; col: number }) => (value: string) => {
    const field = uniqueFields[0];
    if (!field || !value) return null;
    const other = inRange.find(
      (tile) => !(tile.row === except.row && tile.col === except.col) && String(tile[field] ?? "") === value,
    );
    return other ? slotNumber(other.row, other.col, safeCols) : null;
  };

  /** Move the edited tile to another slot; if that slot is taken, swap. */
  const move = (from: { row: number; col: number }, to: { row: number; col: number }) => {
    onChange(
      tiles.map((tile) => {
        if (tile.row === from.row && tile.col === from.col) return { ...tile, row: to.row, col: to.col };
        if (tile.row === to.row && tile.col === to.col) return { ...tile, row: from.row, col: from.col };
        return tile;
      }),
    );
    setEditing(null);
    toast.success(t("tileMoved", { position: slotNumber(to.row, to.col, safeCols) }));
  };

  /** Arrow keys move between slots (the slots stay in the normal tab order). */
  const onSlotKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, row: number, col: number) => {
    const deltas: Record<string, [number, number]> = {
      ArrowRight: [0, 1],
      ArrowLeft: [0, -1],
      ArrowDown: [1, 0],
      ArrowUp: [-1, 0],
    };
    const delta = deltas[event.key];
    if (!delta) return;
    event.preventDefault();
    const nextRow = Math.min(Math.max(row + delta[0], 0), safeRows - 1);
    const nextCol = Math.min(Math.max(col + delta[1], 0), safeCols - 1);
    event.currentTarget
      .closest('[data-testid="tile-grid"]')
      ?.querySelector<HTMLButtonElement>(`[data-testid="tile-slot-${nextRow}-${nextCol}"]`)
      ?.focus();
  };

  return (
    <Stack gap="2" data-testid="tile-grid-assignment">
      <Flex align="center" justify="between" gap="2" wrap>
        <Text as="span" size="xs" weight="medium" role="status" data-testid="tile-grid-progress">
          {assigned === total ? t("tilesComplete", { total }) : t("tilesPartial", { assigned, total })}
        </Text>
        {identify && identifyAll && actions && (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={disabled || assigned === 0 || actions.running !== null}
            onClick={async () => {
              const result = await actions.run(
                "identify",
                { target: "all" },
                { applyFills: false, origin: identifyAllOrigin },
              );
              if (identify) toastActionResult(identify, result, t("actionFailed"));
            }}
          >
            {actions.running === "identify" ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <ScanSearch className="mr-1 h-4 w-4" aria-hidden="true" />
            )}
            {t("identifyAllTiles")}
          </Button>
        )}
      </Flex>
      <Box aria-live="polite">
        {actions?.feedback?.[identifyAllOrigin] && <ActionFeedback entry={actions.feedback[identifyAllOrigin]} />}
      </Box>

      {duplicates.length > 0 && (
        <Flex role="alert" align="center" gap="1.5">
          <AlertCircle className="h-4 w-4 flex-shrink-0 text-warning" aria-hidden="true" />
          <Text as="span" size="xs">
            {t("tilesDuplicate", { values: duplicates.join(", ") })}
          </Text>
        </Flex>
      )}

      <Box
        role="group"
        aria-label={label}
        id={name}
        data-testid="tile-grid"
        className="grid gap-2"
        style={{ gridTemplateColumns: `repeat(${safeCols}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: safeRows }, (_, row) =>
          Array.from({ length: safeCols }, (_, col) => {
            const tile = at(row, col);
            const ready = !!tile && tileReady(tile, itemRequired);
            const position = slotNumber(row, col, safeCols);
            const shown = summary(tile);
            return (
              <Button
                key={`${row}-${col}`}
                type="button"
                variant={ready ? "secondary" : "outline"}
                className="h-auto min-h-12 flex-col gap-0.5 py-2 text-xs"
                disabled={disabled}
                data-testid={`tile-slot-${row}-${col}`}
                data-assigned={ready ? "true" : undefined}
                onClick={() => setEditing({ row, col })}
                onKeyDown={(e) => onSlotKeyDown(e, row, col)}
                aria-label={
                  ready
                    ? t("tileSlotAssigned", {
                        position,
                        row: row + 1,
                        col: col + 1,
                        summary: shown || t("tileAssigned"),
                      })
                    : t("tileSlotEmpty", { position, row: row + 1, col: col + 1 })
                }
              >
                <Text as="span" size="xs" weight="semibold" tone="muted">
                  {position}
                </Text>
                {ready ? (
                  <Text as="span" size="xs" className="max-w-full truncate font-mono">
                    {shown || t("tileAssigned")}
                  </Text>
                ) : (
                  <Text as="span" size="xs" tone="muted" className="flex items-center gap-1">
                    <Plus className="h-3 w-3" aria-hidden="true" />
                    {t("tileAssign")}
                  </Text>
                )}
              </Button>
            );
          }),
        )}
      </Box>

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        {editing && (
          <TileValueInUseContext.Provider value={inUseBy(editing)}>
            <TileDialog
              key={`${editing.row}-${editing.col}`}
              tile={at(editing.row, editing.col) ?? { row: editing.row, col: editing.col }}
              saved={!!at(editing.row, editing.col)}
              position={slotNumber(editing.row, editing.col, safeCols)}
              rows={safeRows}
              cols={safeCols}
              occupant={(row, col) => summary(at(row, col))}
              itemProperties={itemProperties}
              itemRequired={itemRequired}
              itemActions={itemActions}
              renderTileFields={renderTileFields}
              renderActionInput={renderActionInput}
              onSave={(tile) => replace(tile, editing)}
              onRemove={() => replace(null, editing)}
              onMove={(to) => move(editing, to)}
            />
          </TileValueInUseContext.Provider>
        )}
      </Dialog>
    </Stack>
  );
}

function TileDialog({
  tile,
  saved,
  position,
  rows,
  cols,
  occupant,
  itemProperties,
  itemRequired,
  itemActions,
  renderTileFields,
  renderActionInput,
  onSave,
  onRemove,
  onMove,
}: {
  tile: Tile;
  saved: boolean;
  position: number;
  rows: number;
  cols: number;
  occupant: (row: number, col: number) => string;
  itemProperties: Record<string, ItemProperty>;
  itemRequired: string[];
  itemActions: string[];
  renderTileFields: TileGridFieldProps["renderTileFields"];
  renderActionInput: TileGridFieldProps["renderActionInput"];
  onSave: (tile: Tile) => void;
  onRemove: () => void;
  onMove: (to: { row: number; col: number }) => void;
}) {
  const t = useTranslations("boardSettingsScreen");
  const tc = useTranslations("common");
  const actions = useBoardActions();
  const [draft, setDraft] = useState<Tile>(tile);
  const [filled, setFilled] = useState<string[]>([]);
  // An action that needs more than the tile holds (Vestaboard's enablement
  // token) asks for it right here, in the tile's own dialog.
  const [asking, setAsking] = useState<{ action: OutputActionDescriptor; input: Record<string, unknown> } | null>(null);
  const declared = itemActions
    .map((id) => actions?.actions.find((a) => a.id === id))
    .filter((a): a is OutputActionDescriptor => !!a);

  /** The part of an action's input schema the tile cannot fill. */
  const extraSchema = (action: OutputActionDescriptor): Record<string, unknown> => {
    const schema = (action.input_schema ?? {}) as { properties?: Record<string, unknown>; required?: unknown[] };
    const properties = Object.fromEntries(
      Object.entries(schema.properties ?? {}).filter(
        ([name]) => !(name in itemProperties) && name !== "row" && name !== "col",
      ),
    );
    const required = (schema.required ?? []).filter((name) => typeof name === "string" && name in properties);
    return { type: "object", properties, required };
  };

  const runOnTile = (action: OutputActionDescriptor) => {
    const input = tileActionInput(action, draft);
    if (missingInputs(action, input).length > 0) setAsking({ action, input });
    else void execute(action, input);
  };

  const execute = async (action: OutputActionDescriptor, input: Record<string, unknown>) => {
    if (!actions) return;
    setAsking(null);
    const result = await actions.run(action.id, input, { applyFills: false, origin: "tile-dialog" });
    toastActionResult(action, result, t("actionFailed"));
    const fills: Record<string, unknown> = {};
    for (const [name, field] of Object.entries(result?.fields ?? {})) {
      const target = field.fills ?? name;
      if (target in itemProperties) fills[target] = field.value;
    }
    if (Object.keys(fills).length > 0) {
      setDraft((current) => ({ ...current, ...fills }));
      setFilled(Object.keys(fills).map((name) => itemProperties[name]?.title || name));
    }
  };

  const others = Array.from({ length: rows }, (_, row) => Array.from({ length: cols }, (_, col) => ({ row, col })))
    .flat()
    .filter(({ row, col }) => !(row === tile.row && col === tile.col));

  return (
    <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
      <DialogHeader>
        <DialogTitle>{t("tileDialogTitle", { position, row: tile.row + 1, col: tile.col + 1 })}</DialogTitle>
        <DialogDescription>{t("tileDialogDescription")}</DialogDescription>
      </DialogHeader>
      <Grid gap="4">
        {renderTileFields(draft, (next) => setDraft({ ...next, row: tile.row, col: tile.col }))}
        {filled.length > 0 && (
          <Text size="xs" role="status">
            {t("fieldsFilled", { fields: filled.join(", ") })}
          </Text>
        )}
        {asking && (
          <Stack gap="2" role="group" aria-label={asking.action.label} className="rounded-md border p-3">
            {renderActionInput(asking.action, extraSchema(asking.action), asking.input, (input) =>
              setAsking({ ...asking, input }),
            )}
            <Flex gap="2" justify="end">
              <Button type="button" variant="ghost" size="sm" onClick={() => setAsking(null)}>
                {tc("cancel")}
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={missingInputs(asking.action, asking.input).length > 0}
                onClick={() => void execute(asking.action, asking.input)}
              >
                {tc("next")}
              </Button>
            </Flex>
          </Stack>
        )}
        {declared.length > 0 && actions && (
          <Flex gap="2" wrap role="group" aria-label={t("tileActionsLabel")}>
            {declared.map((action) => (
              <Button
                key={action.id}
                type="button"
                variant="outline"
                size="sm"
                disabled={actions.running !== null}
                aria-busy={actions.running === action.id}
                title={action.description || undefined}
                onClick={() => runOnTile(action)}
              >
                {actions.running === action.id && <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden="true" />}
                {action.label}
              </Button>
            ))}
          </Flex>
        )}
        {saved && others.length > 0 && (
          <Grid gap="1.5">
            <Label htmlFor={`tile-move-${tile.row}-${tile.col}`}>{t("moveTile")}</Label>
            <Select
              value=""
              onValueChange={(next) => {
                const [row, col] = String(next).split(":").map(Number);
                if (Number.isInteger(row) && Number.isInteger(col)) onMove({ row, col });
              }}
            >
              <SelectTrigger id={`tile-move-${tile.row}-${tile.col}`}>
                <SelectValue placeholder={t("movePlaceholder")} />
              </SelectTrigger>
              {/* Above the dialog overlay — the shared default would render underneath it. */}
              <SelectContent className="z-[140]">
                {others.map(({ row, col }) => {
                  const there = occupant(row, col);
                  const slot = slotNumber(row, col, cols);
                  return (
                    <SelectItem key={`${row}:${col}`} value={`${row}:${col}`}>
                      {there ? t("moveSwap", { position: slot, summary: there }) : t("moveTo", { position: slot })}
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </Grid>
        )}
      </Grid>
      <DialogFooter>
        {saved && (
          <Button type="button" variant="ghost" onClick={onRemove}>
            <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
            {t("removeTile")}
          </Button>
        )}
        <Button type="button" disabled={!tileReady(draft, itemRequired)} onClick={() => onSave(draft)}>
          {t("saveTile")}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
