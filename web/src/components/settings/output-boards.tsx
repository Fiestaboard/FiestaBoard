"use client";

/**
 * Boards and their outputs (plan D13), on a display's page (plan D21):
 *
 * - {@link OutputBoardSettings}: a saved board's connection screen — any
 *   output's, the Vestaboard's included — drawn from its manifest and saved
 *   with the board settings (`output_config`, secrets echoed as `"***"`).
 *   A first-party output's screen saves as its hand-coded form always did:
 *   a typed field when it loses focus, anything else (a mode card, a tile,
 *   a filled-in key) at once. A third-party output's has a Save button.
 */
import { Alert, AlertDescription, Box, Button, Stack } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { Cpu, Grid3x3, LayoutGrid, Lightbulb, type LucideIcon, Monitor, MonitorSmartphone, Tv } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import type { ActionGeometry, BoardInstance } from "@/lib/api";
import { api } from "@/lib/api";
import { isNoteArray } from "@/lib/board-dimensions";
import type { BoardFacts } from "@/lib/visible-when";

import { PluginBoardSettings } from "./plugin-board-settings";

export const OUTPUTS_QUERY_KEY = ["outputs"] as const;
/** `GET /outputs/available`: installed or not (the setup wizard's choices). */
export const AVAILABLE_OUTPUTS_QUERY_KEY = ["outputs", "available"] as const;

/** The outputs this install has (`GET /outputs`). */
export function useOutputs() {
  return useQuery({ queryKey: OUTPUTS_QUERY_KEY, queryFn: () => api.listOutputs(), staleTime: 60_000 });
}

/** A board an output plugin drives: neither a Vestaboard nor a FiestaPanel. */
export function isPluginOutputBoard(board: Pick<BoardInstance, "output">): boolean {
  return !!board.output && board.output !== "vestaboard" && board.output !== "fiestapanel";
}

/** A FiestaPanel's board: drawn in memory, nothing to connect to. */
export function isVirtualBoard(board: Pick<BoardInstance, "output" | "api_mode">): boolean {
  return board.output ? board.output === "fiestapanel" : board.api_mode === "virtual";
}

/**
 * The settings-v3 flat connection fields every board still *reads* back with
 * (a compatibility view for other clients). Settings v4 stores them in the
 * board's `output_config`, which is what this app writes.
 */
const FLAT_CONNECTION_FIELDS = [
  "api_mode",
  "host",
  "port",
  "local_api_key",
  "cloud_key",
  "note_array_token",
  "tiles",
] as const;

/** *board* as this app writes it: the settings-v4 shape, its connection in `output_config` only. */
export function toV4Write(board: BoardInstance): BoardInstance {
  const out = { ...board } as Record<string, unknown>;
  for (const field of FLAT_CONNECTION_FIELDS) delete out[field];
  return out as unknown as BoardInstance;
}

/** What a board's settings screen reads as `@device_type` / `@device_model`. */
export function boardFacts(board: Pick<BoardInstance, "device_type" | "device_model">): BoardFacts {
  return { device_type: board.device_type ?? null, device_model: board.device_model ?? null };
}

/** A note array's tile layout (Notes down × across); `null` for any other board. */
export function boardLayout(
  board: Pick<BoardInstance, "device_type" | "notes_wide" | "notes_tall">,
): { rows: number; cols: number } | null {
  return isNoteArray(board.device_type) ? { rows: board.notes_tall ?? 1, cols: board.notes_wide ?? 1 } : null;
}

const ICONS: Record<string, LucideIcon> = {
  cpu: Cpu,
  "grid-3x3": Grid3x3,
  "layout-grid": LayoutGrid,
  lightbulb: Lightbulb,
  monitor: Monitor,
  tv: Tv,
};

/** The Lucide icon a manifest names, from a small known set; a generic display otherwise. */
export function OutputIcon({ name, className }: { name: string | null | undefined; className?: string }) {
  const Icon = (name && ICONS[name]) || MonitorSmartphone;
  return <Icon className={className ?? "h-4 w-4"} aria-hidden="true" />;
}

/** Whether *element* takes typed text: such a field saves when it loses focus. */
function isTypingField(element: Element | null): boolean {
  if (element instanceof HTMLTextAreaElement) return true;
  if (!(element instanceof HTMLInputElement)) return false;
  return !["checkbox", "radio", "button", "submit", "reset", "range", "color", "file"].includes(element.type);
}

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * The settings to show after the stored ones changed underneath an edit: a
 * field the user has not touched since the last sync takes the stored value
 * (the server normalised it, or masked a key it now holds); one they have
 * keeps what they typed.
 */
export function mergeStored(
  values: Record<string, unknown>,
  synced: Record<string, unknown>,
  stored: Record<string, unknown>,
): Record<string, unknown> {
  const next: Record<string, unknown> = {};
  for (const key of new Set([...Object.keys(stored), ...Object.keys(values)])) {
    const edited = key in values && !same(values[key], synced[key]);
    if (edited) next[key] = values[key];
    else if (key in stored) next[key] = stored[key];
  }
  return next;
}

export function OutputBoardSettings({
  board,
  onSave,
  saving,
  onGeometry,
  autosave,
}: {
  board: BoardInstance;
  onSave: (outputConfig: Record<string, unknown>) => void;
  saving: boolean;
  /** Apply a size the output's detect action read (a Vestaboard's type and size are the board's). */
  onGeometry?: (geometry: ActionGeometry) => void;
  /**
   * Save as the user goes — a typed field on blur, any other change at once —
   * instead of with a Save button. Defaults to the first-party outputs' way
   * (their hand-coded forms always saved like this); a third-party output's
   * screen keeps its Save button.
   */
  autosave?: boolean;
}) {
  const t = useTranslations("boardSettingsScreen");
  const tc = useTranslations("common");
  const { data: outputs, isLoading } = useOutputs();
  const stored = (board.output_config ?? {}) as Record<string, unknown>;
  const [values, setValues] = useState<Record<string, unknown>>(stored);
  const [synced, setSynced] = useState<Record<string, unknown>>(stored);
  // A typed edit not yet saved: it saves when its field loses focus.
  const pending = useRef(false);
  const latest = useRef(values);
  useEffect(() => {
    latest.current = values;
  }, [values]);
  const output = outputs?.find((o) => o.id === (board.output ?? "vestaboard"));
  const saves = autosave ?? output?.builtin ?? false;

  // The stored settings changed (a save came back, or another client saved):
  // adopt them, keeping whatever the user has edited since the last sync.
  if (!same(stored, synced)) {
    setSynced(stored);
    setValues(mergeStored(values, synced, stored));
  }

  if (isLoading) return null;
  if (!output) {
    return (
      <Alert variant="warning" data-testid="output-not-installed">
        <AlertDescription>{t("outputNotInstalled", { output: board.output ?? "" })}</AlertDescription>
      </Alert>
    );
  }
  const dirty = !same(values, stored);

  const commit = (next: Record<string, unknown>) => {
    pending.current = false;
    if (!same(next, stored)) onSave(next);
  };

  const onChange = (next: Record<string, unknown>) => {
    setValues(next);
    latest.current = next;
    if (!saves) return;
    if (isTypingField(document.activeElement)) pending.current = true;
    else commit(next);
  };

  return (
    <Stack
      gap="3"
      onBlur={
        saves
          ? (event: React.FocusEvent) => {
              if (pending.current && isTypingField(event.target)) commit(latest.current);
            }
          : undefined
      }
    >
      <PluginBoardSettings
        output={output}
        values={values}
        onChange={onChange}
        boardId={board.id}
        facts={boardFacts(board)}
        layout={boardLayout(board)}
        onGeometry={onGeometry}
      />
      {!saves && (
        <Box>
          <Button type="button" size="sm" disabled={!dirty || saving} onClick={() => onSave(values)}>
            {saving ? tc("saving") : t("saveSettings")}
          </Button>
        </Box>
      )}
    </Stack>
  );
}
