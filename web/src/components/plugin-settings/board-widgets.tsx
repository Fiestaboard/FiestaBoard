"use client";

/**
 * The core board-setup widgets of the settings contract (plan D13) — a
 * closed set, built from @fiestaboard/ui primitives; a plugin declares them
 * in its schema and never ships UI code:
 *
 * - `mode-cards`: a string `enum` as a radiogroup of cards
 *   (`ui:options.cards: [{value, title, description}]`).
 * - `device-picker`: a text field plus "Find devices", which runs the
 *   output's discover action (`ui:options.action`) and offers what it found.
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
import { AlertCircle, Loader2, Plus, ScanSearch, Search, Trash2 } from "lucide-react";
import React, { createContext, useContext, useMemo, useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import type { ActionResult, DiscoveredDevice, OutputActionDescriptor } from "@/lib/api";

/** How a widget runs an action. */
export interface RunOptions {
  /**
   * Fill the result's `fields` into the screen's settings (default). A tile
   * action passes `false`: its fills belong to the tile, not the board.
   */
  applyFills?: boolean;
}

/** What the board settings screen lends its widgets: the declared actions and a runner. */
export interface BoardActionsContextValue {
  actions: OutputActionDescriptor[];
  /** Runs one action (saved or draft route, as the screen decides); `null` when it threw. */
  run: (actionId: string, input?: Record<string, unknown>, options?: RunOptions) => Promise<ActionResult | null>;
  /** The action in flight, if any. */
  running: string | null;
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
  onChange: (value: unknown) => void;
  placeholder?: string;
  action?: string;
  valueKey?: string;
  labelKey?: string;
  disabled?: boolean;
  required?: boolean;
}

function deviceText(device: DiscoveredDevice, key: string): string {
  const raw = (device as unknown as Record<string, unknown>)[key];
  return raw === undefined || raw === null ? "" : String(raw);
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
  disabled,
  required,
}: DevicePickerFieldProps) {
  const t = useTranslations("boardSettingsScreen");
  const actions = useBoardActions();
  const inUse = useContext(TileValueInUseContext);
  const [devices, setDevices] = useState<DiscoveredDevice[] | null>(null);
  const canScan = actions?.actions.some((a) => a.id === action) ?? false;
  const scanning = actions?.running === action;

  const scan = async () => {
    if (!actions) return;
    const result = await actions.run(action);
    if (result === null) toast.error(t("actionFailed"));
    setDevices(result?.devices ?? []);
  };

  return (
    <Stack gap="2">
      <Flex gap="2">
        <Input
          id={name}
          type="text"
          value={String(value ?? "")}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          required={required}
          className="flex-1"
        />
        {canScan && (
          <Button type="button" variant="secondary" onClick={() => void scan()} disabled={disabled || scanning}>
            {scanning ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Search className="mr-1 h-4 w-4" />}
            {scanning ? t("scanning") : t("scanDevices")}
          </Button>
        )}
      </Flex>
      {devices !== null &&
        (devices.length === 0 ? (
          <Text size="xs" tone="muted" role="status">
            {t("noDevicesFound")}
          </Text>
        ) : (
          <ToggleCardGroup
            size="sm"
            columns="1"
            value={String(value ?? "")}
            onValueChange={(next) => onChange(next)}
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
        ))}
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
              const result = await actions.run("identify", { target: "all" }, { applyFills: false });
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
    const result = await actions.run(action.id, input, { applyFills: false });
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
