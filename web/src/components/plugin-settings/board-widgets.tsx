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
 *   (`ui:options.rows_field` / `cols_field` size it); each slot opens a
 *   dialog with the item's other fields, and Identify when the output
 *   declares it.
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
  Stack,
  Text,
  ToggleCard,
  ToggleCardGroup,
} from "@fiestaboard/ui";
import { Loader2, Search } from "lucide-react";
import React, { createContext, useContext, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import type { ActionResult, DiscoveredDevice, OutputActionDescriptor } from "@/lib/api";

/** What the board settings screen lends its widgets: the declared actions and a runner. */
export interface BoardActionsContextValue {
  actions: OutputActionDescriptor[];
  /** Runs one action (saved or draft route, as the screen decides); `null` when it threw. */
  run: (actionId: string, input?: Record<string, unknown>) => Promise<ActionResult | null>;
  /** The action in flight, if any. */
  running: string | null;
}

export const BoardActionsContext = createContext<BoardActionsContextValue | null>(null);

export function useBoardActions(): BoardActionsContextValue | null {
  return useContext(BoardActionsContext);
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
  const [devices, setDevices] = useState<DiscoveredDevice[] | null>(null);
  const canScan = actions?.actions.some((a) => a.id === action) ?? false;
  const scanning = actions?.running === action;

  const scan = async () => {
    if (!actions) return;
    const result = await actions.run(action);
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
              return (
                <ToggleCard
                  key={`${deviceValue}:${device.port}`}
                  value={deviceValue}
                  title={deviceText(device, labelKey) || device.label || deviceValue}
                  description={`${device.ip}:${device.port}`}
                />
              );
            })}
          </ToggleCardGroup>
        ))}
    </Stack>
  );
}

interface TileGridFieldProps {
  name: string;
  label: string;
  value: unknown;
  onChange: (value: unknown) => void;
  rows: number;
  cols: number;
  /** Renders the form for a tile's own fields (everything but row/col). */
  renderTileFields: (
    tile: Record<string, unknown>,
    onTileChange: (tile: Record<string, unknown>) => void,
  ) => React.ReactNode;
  disabled?: boolean;
}

type Tile = Record<string, unknown> & { row: number; col: number };

function asTiles(value: unknown): Tile[] {
  return Array.isArray(value)
    ? value.filter(
        (t): t is Tile =>
          !!t && typeof t === "object" && typeof (t as Tile).row === "number" && typeof (t as Tile).col === "number",
      )
    : [];
}

export function TileGridField({
  name,
  label,
  value,
  onChange,
  rows,
  cols,
  renderTileFields,
  disabled,
}: TileGridFieldProps) {
  const t = useTranslations("boardSettingsScreen");
  const actions = useBoardActions();
  const tiles = asTiles(value);
  const [editing, setEditing] = useState<Tile | null>(null);
  const canIdentify = actions?.actions.some((a) => a.id === "identify") ?? false;

  const at = (row: number, col: number) => tiles.find((tile) => tile.row === row && tile.col === col);

  const save = (tile: Tile) => {
    const others = tiles.filter((x) => !(x.row === tile.row && x.col === tile.col));
    onChange([...others, tile]);
    setEditing(null);
  };

  const remove = (tile: Tile) => {
    onChange(tiles.filter((x) => !(x.row === tile.row && x.col === tile.col)));
    setEditing(null);
  };

  const safeRows = Math.max(1, Math.min(rows, 12));
  const safeCols = Math.max(1, Math.min(cols, 12));

  return (
    <Stack gap="2">
      <Box
        role="group"
        aria-label={label}
        id={name}
        className="grid gap-2"
        style={{ gridTemplateColumns: `repeat(${safeCols}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: safeRows }, (_, row) =>
          Array.from({ length: safeCols }, (_, col) => {
            const tile = at(row, col);
            return (
              <Button
                key={`${row}-${col}`}
                type="button"
                variant={tile ? "secondary" : "outline"}
                className="h-auto min-h-12 flex-col py-2 text-xs"
                disabled={disabled}
                onClick={() => setEditing(tile ?? { row, col })}
                aria-label={t("tileSlot", { row: row + 1, col: col + 1 })}
              >
                <Text as="span" size="xs" weight="medium">
                  {row + 1},{col + 1}
                </Text>
                <Text as="span" size="xs" tone="muted">
                  {tile ? t("tileAssigned") : t("tileEmpty")}
                </Text>
              </Button>
            );
          }),
        )}
      </Box>
      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        {editing && (
          <TileDialog
            key={`${editing.row}-${editing.col}`}
            tile={editing}
            assigned={!!at(editing.row, editing.col)}
            canIdentify={canIdentify}
            renderTileFields={renderTileFields}
            onSave={save}
            onRemove={remove}
          />
        )}
      </Dialog>
    </Stack>
  );
}

/**
 * The identify action's input for one tile: only the keys its `input_schema`
 * declares. A tile whose credentials read back masked (`"***"`, a saved
 * tile) is identified by position alone, so the server flashes the stored
 * tile rather than sending three asterisks as a key.
 */
export function identifyInput(actions: OutputActionDescriptor[], tile: Tile): Record<string, unknown> | undefined {
  const schema = actions.find((a) => a.id === "identify")?.input_schema;
  const declared = (schema?.properties ?? null) as Record<string, unknown> | null;
  if (!declared) return undefined;
  const masked = Object.values(tile).some((v) => v === "***");
  const source: Record<string, unknown> = masked
    ? { target: "tile", row: tile.row, col: tile.col }
    : { target: "tile", ...tile };
  return Object.fromEntries(
    Object.entries(source).filter(([key, v]) => key in declared && v !== undefined && v !== ""),
  );
}

function TileDialog({
  tile,
  assigned,
  canIdentify,
  renderTileFields,
  onSave,
  onRemove,
}: {
  tile: Tile;
  assigned: boolean;
  canIdentify: boolean;
  renderTileFields: TileGridFieldProps["renderTileFields"];
  onSave: (tile: Tile) => void;
  onRemove: (tile: Tile) => void;
}) {
  const t = useTranslations("boardSettingsScreen");
  const tc = useTranslations("common");
  const actions = useBoardActions();
  const [draft, setDraft] = useState<Tile>(tile);
  const identifying = actions?.running === "identify";

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{t("tileDialogTitle", { row: tile.row + 1, col: tile.col + 1 })}</DialogTitle>
        <DialogDescription>{t("tileDialogDescription")}</DialogDescription>
      </DialogHeader>
      <Grid gap="4">{renderTileFields(draft, (next) => setDraft({ ...next, row: tile.row, col: tile.col }))}</Grid>
      <DialogFooter>
        {assigned && (
          <Button type="button" variant="ghost" onClick={() => onRemove(tile)}>
            {t("removeTile")}
          </Button>
        )}
        {canIdentify && actions && (
          <Button
            type="button"
            variant="secondary"
            disabled={identifying}
            onClick={() => void actions.run("identify", identifyInput(actions.actions, draft))}
          >
            {identifying && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {t("identifyTile")}
          </Button>
        )}
        <Button type="button" onClick={() => onSave(draft)}>
          {tc("save")}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
