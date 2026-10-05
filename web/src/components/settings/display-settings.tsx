"use client";

/**
 * A display's (board's) own settings, as the Displays section (plan D21)
 * shows them:
 *
 * - {@link useDisplayBoards}: the boards, their status, and the writes every
 *   display screen shares (rename, resize, pause, remove, add).
 * - {@link BoardStatusBadges} / {@link BoardSummary}: a display's name,
 *   shape and state, for its card on /displays and its page's header.
 * - {@link BoardEditor}: everything one display's page edits — name, pause,
 *   a Vestaboard's type, colour and code-62 flap, the output's own settings
 *   screen (plan D13), and removing it.
 * - {@link VestaboardTypeButtons}: the Vestaboard shapes "Add a display"
 *   offers.
 */

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge as BadgeUI,
  Box,
  Button,
  Flex,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, Check, LayoutGrid, Monitor, Pause, Smartphone, Trash2, Tv } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { BoardSizeIndicator } from "@/components/board-size-indicator";
import { queryKeys, useBoardSettings, useStatus } from "@/hooks/use-board";
import { PANELS_QUERY_KEY } from "@/hooks/use-panel-targets";
import { useTranslations } from "@/i18n/translations";
import type { ActionGeometry, BoardInstance, BoardStatus, Code62Glyph, DeviceType } from "@/lib/api";
import { api } from "@/lib/api";
import { MAX_BOARD_NAME_LENGTH, MAX_NOTES_PER_AXIS, NOTE_ARRAY_PRESETS } from "@/lib/board-dimensions";

import { isPluginOutputBoard, isVirtualBoard, OutputBoardSettings, toV4Write } from "./output-boards";

/**
 * The two flaps a Flagship's character-code-62 slot can physically carry
 * (issue #1657). Module scope so the swatch pair below has one source of truth
 * and a stable identity across renders.
 */
const CODE62_CHOICES: ReadonlyArray<{ value: Code62Glyph; glyph: string; labelKey: string }> = [
  { value: "degree", glyph: "°", labelKey: "code62DegreeAriaLabel" },
  { value: "heart", glyph: "♥", labelKey: "code62HeartAriaLabel" },
];

/**
 * Controlled board display-name field (issue #1792).
 *
 * The stored name is normalized by the backend (trimmed, capped, empty →
 * "My Board"), so the field cannot be uncontrolled: after clearing the name
 * the input would keep showing "" while the board is actually called
 * "My Board". That stale value also makes the blur handler see a change every
 * time, firing an identical PUT on each focus/blur — and every PUT re-runs
 * `_reinitialize_board_clients()` and rewrites config.json.
 *
 * So: local draft state for typing, re-synced whenever the server's name
 * changes underneath it.
 */
function BoardNameField({ board, onRename }: { board: BoardInstance; onRename: (name: string) => void }) {
  const t = useTranslations("displaySettings");
  const storedName = board.name ?? "";
  const [draft, setDraft] = useState(storedName);
  const [syncedFrom, setSyncedFrom] = useState(storedName);

  // Adjust state during render rather than in an effect: when the refetch
  // brings back a different name (the server-normalized one), adopt it.
  if (storedName !== syncedFrom) {
    setSyncedFrom(storedName);
    setDraft(storedName);
  }

  const handleBlur = () => {
    const trimmed = draft.trim();
    // Show what will actually be stored, so re-blurring is a no-op.
    setDraft(trimmed);
    if (trimmed !== storedName) {
      onRename(trimmed);
    }
  };

  return (
    <Stack gap="1">
      <label className="text-xs font-medium" htmlFor={`board-name-${board.id}`}>
        {t("boardNameLabel")}
      </label>
      <input
        id={`board-name-${board.id}`}
        type="text"
        value={draft}
        // Matches the backend cap, so the field never shows more than what
        // will actually be stored.
        maxLength={MAX_BOARD_NAME_LENGTH}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={handleBlur}
        placeholder={t("boardNamePlaceholder")}
        className="w-full h-8 px-2 text-xs rounded-md border bg-background"
        data-testid="board-name-input"
      />
    </Stack>
  );
}

/** The boards, their status, and the writes every display screen shares. */
export function useDisplayBoards() {
  const t = useTranslations("displaySettings");
  const queryClient = useQueryClient();
  const { data: boardSettings, isLoading } = useBoardSettings();
  // Per-board init errors and output status from the shared status poll
  // (issues #1829, plan D13 `status`).
  const { data: statusData } = useStatus();
  const boards = boardSettings?.boards ?? [];

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
    queryClient.invalidateQueries({ queryKey: ["all-settings"] });
    // Board count and device type affect template rendering dimensions
    // and which board previews are shown, so refresh previews and displays.
    queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
    queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
    // The Connected / Not configured badge is the output's status on the
    // status poll: refresh it with the settings it reads.
    queryClient.invalidateQueries({ queryKey: queryKeys.status });
  };

  const updateMutation = useMutation({
    mutationFn: (updates: { board_type?: "black" | "white" | null; boards?: BoardInstance[] }) =>
      api.updateBoardSettings(updates),
    onSuccess: invalidate,
    onError: (error: Error) => toast.error(error.message),
  });

  const addMutation = useMutation({
    mutationFn: (board: Partial<BoardInstance> & { device_type: DeviceType }) => api.addBoard(board),
    onSuccess: () => {
      invalidate();
      toast.success(t("boardAdded"));
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const removeMutation = useMutation({
    mutationFn: (boardId: string) => api.removeBoard(boardId),
    onSuccess: () => {
      invalidate();
      toast.success(t("boardRemoved"));
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const pauseMutation = useMutation({
    mutationFn: ({ boardId, paused }: { boardId: string; paused: boolean }) => api.setBoardPaused(boardId, paused),
    onSuccess: invalidate,
    onError: (error: Error) => toast.error(error.message),
  });

  // Panels, to recognize which virtual board backs which FiestaPanel: its
  // page must not offer credentials, and removing it out from under a live
  // panel (blanking the TV) is blocked — the panel editor owns that board.
  const { data: panelsData } = useQuery({
    queryKey: PANELS_QUERY_KEY,
    queryFn: () => api.listPanels(),
  });
  const panelNameByBoardId = new Map((panelsData?.panels ?? []).map((p) => [p.board_id, p.name]));

  return {
    boards,
    isLoading,
    /** A board's slice of the status poll, if any. */
    statusFor: (boardId: string): BoardStatus | undefined => statusData?.boards?.[boardId],
    panelNameByBoardId,
    saving: updateMutation.isPending,
    /**
     * Writes in the settings-v4 shape: each board's connection travels in its
     * `output_config` only (the flat fields the API still answers with are a
     * compatibility view for other clients).
     */
    updateBoard: (boardId: string, updates: Partial<BoardInstance>) => {
      const updated = boards.map((b) => toV4Write(b.id === boardId ? { ...b, ...updates } : b));
      updateMutation.mutate({ boards: updated });
    },
    /** Remove a board; the last one stays. Resolves true once it is gone. */
    removeBoard: async (boardId: string): Promise<boolean> => {
      if (boards.length <= 1) {
        toast.error(t("atLeastOneBoard"));
        return false;
      }
      try {
        await removeMutation.mutateAsync(boardId);
        return true;
      } catch {
        return false;
      }
    },
    setPaused: (boardId: string, paused: boolean) => pauseMutation.mutate({ boardId, paused }),
    pausePending: pauseMutation.isPending,
    /** Add a Vestaboard of *deviceType*; resolves to the new board's id. */
    addVestaboard: async (deviceType: DeviceType): Promise<string | null> => {
      // Arrays start as the smallest real layout (the "2 side-by-side"
      // preset) in cloud mode — they're driven via the Cloud API today.
      const board: Partial<BoardInstance> & { device_type: DeviceType } =
        deviceType === "note_array"
          ? {
              device_type: "note_array",
              notes_wide: 2,
              notes_tall: 1,
              output: "vestaboard",
              output_config: { api_mode: "cloud" },
            }
          : { device_type: deviceType };
      try {
        const settings = await addMutation.mutateAsync(board);
        return settings.boards[settings.boards.length - 1]?.id ?? null;
      } catch {
        return null;
      }
    },
    adding: addMutation.isPending,
  };
}

export type DisplayBoards = ReturnType<typeof useDisplayBoards>;

/** A display's state: unavailable, paused, a panel's, connected or not configured. */
export function BoardStatusBadges({ board, status }: { board: BoardInstance; status: BoardStatus | undefined }) {
  const t = useTranslations("displaySettings");
  // Why this board has no client, when the backend skipped it at startup
  // (issues #1749/#1829). Verbatim backend reason string.
  const initError = status?.error ?? null;
  // Connected / Not configured is the board's output's own summary of its
  // settings (plan D13 `status`); an output with nothing to say shows none.
  const outputStatus = status?.output_status ?? null;
  return (
    <Flex align="center" gap="1.5" wrap className="flex-shrink-0">
      {initError && (
        <BadgeUI
          variant="destructive"
          className="text-[10px] h-5"
          data-testid="board-init-error-badge"
          title={initError}
        >
          <AlertTriangle className="h-2.5 w-2.5 mr-0.5" />
          {t("initError.badge")}
        </BadgeUI>
      )}
      {board.paused === true && (
        <BadgeUI
          variant="default"
          className="text-[10px] h-5 bg-warning text-warning-foreground"
          data-testid="board-paused-badge"
          title={t("pause.tooltip")}
        >
          <Pause className="h-2.5 w-2.5 mr-0.5" />
          {t("pause.badge")}
        </BadgeUI>
      )}
      {isVirtualBoard(board) ? (
        <BadgeUI variant="secondary" className="text-[10px] h-5" data-testid="board-virtual-badge">
          <Tv className="h-2.5 w-2.5 mr-0.5" />
          {t("virtualBadge")}
        </BadgeUI>
      ) : outputStatus?.state === "connected" ? (
        <BadgeUI
          variant="default"
          className="text-[10px] h-5 bg-board-green"
          data-testid="board-status-badge"
          data-state="connected"
          title={outputStatus.message || undefined}
        >
          <Check className="h-2.5 w-2.5 mr-0.5" />
          {t("connected")}
        </BadgeUI>
      ) : outputStatus?.state === "not_configured" ? (
        <BadgeUI
          variant="destructive"
          className="text-[10px] h-5"
          data-testid="board-status-badge"
          data-state="not_configured"
          title={outputStatus.message || undefined}
        >
          <AlertCircle className="h-2.5 w-2.5 mr-0.5" />
          {t("notConfigured")}
        </BadgeUI>
      ) : null}
    </Flex>
  );
}

/** A display's shape: its device type, its size and its colour. */
export function BoardSummary({ board }: { board: BoardInstance }) {
  return (
    <Flex align="center" gap="2" className="text-xs text-muted-foreground">
      <Text as="span" size="xs" className="capitalize">
        {board.device_type}
      </Text>
      <Text as="span" size="xs" tone="muted" aria-hidden="true">
        •
      </Text>
      <BoardSizeIndicator
        deviceType={board.device_type}
        notesWide={board.notes_wide}
        notesTall={board.notes_tall}
        gridRows={board.grid_rows}
        gridCols={board.grid_cols}
      />
      <Text as="span" size="xs" tone="muted" aria-hidden="true">
        •
      </Text>
      <Box
        aria-hidden="true"
        className="h-3 w-3 rounded border"
        style={{
          backgroundColor:
            board.board_color === "white" ? "var(--color-board-surface-light)" : "var(--color-board-surface-dark)",
        }}
      />
    </Flex>
  );
}

/**
 * Everything one display's page edits. Saves as the settings page always
 * did: at once, a typed field when it loses focus.
 */
export function BoardEditor({
  board,
  displays,
  onRemoved,
}: {
  board: BoardInstance;
  displays: DisplayBoards;
  /** The board is gone (the page it was on should go too). */
  onRemoved?: () => void;
}) {
  const t = useTranslations("displaySettings");
  // The note-array selector's custom inputs and their range error.
  const [customOpen, setCustomOpen] = useState(false);
  const [dimError, setDimError] = useState<string | undefined>(undefined);
  const { boards, updateBoard } = displays;
  const status = displays.statusFor(board.id);
  const isPaused = board.paused === true;
  // Virtual boards (FiestaPanel) render to memory: there is no connection
  // to configure, so none of the credential/type controls apply (issue: a
  // freshly created panel showed as needing API credentials).
  const isVirtual = isVirtualBoard(board);
  // A board an output plugin drives is sized by its device model; a
  // Vestaboard's type and size stay core's (below).
  const isPluginOutput = isPluginOutputBoard(board);
  const panelName = isVirtual ? displays.panelNameByBoardId.get(board.id) : undefined;
  const initError = status?.error ?? null;
  const update = (updates: Partial<BoardInstance>) => updateBoard(board.id, updates);

  /** A board turning into a note array lands in cloud mode — the array default. */
  const cloudOnConvert = (): Partial<BoardInstance> =>
    board.device_type !== "note_array" ? { output_config: { ...(board.output_config ?? {}), api_mode: "cloud" } } : {};

  // Map the board to the synthetic Select value. Note arrays whose dims match
  // a preset resolve to that preset; otherwise to "custom". (Match by
  // dimensions, never by the detect endpoint's `matched_preset` label.)
  const currentConfigValue = (): string => {
    if (board.device_type !== "note_array") return board.device_type; // "flagship" | "note"
    const match = NOTE_ARRAY_PRESETS.find(
      (p) => p.notes_wide === (board.notes_wide ?? 1) && p.notes_tall === (board.notes_tall ?? 1),
    );
    return match ? `preset:${match.id}` : "custom";
  };

  const handleConfigChange = (value: string) => {
    if (value === "flagship" || value === "note") {
      setCustomOpen(false);
      update({ device_type: value });
      return;
    }
    // Converting a single board (whose api_mode defaults to "local") into an
    // array must land in cloud mode — the array default. An existing array
    // keeps whatever mode the user picked; only its size changes.
    const modeOnConvert = cloudOnConvert();
    if (value === "custom") {
      setCustomOpen(true);
      const w = board.device_type === "note_array" ? (board.notes_wide ?? 1) : 1;
      const h = board.device_type === "note_array" ? (board.notes_tall ?? 1) : 1;
      update({ device_type: "note_array", notes_wide: w, notes_tall: h, ...modeOnConvert });
      return;
    }
    // value === "preset:<id>"
    setCustomOpen(false);
    const preset = NOTE_ARRAY_PRESETS.find((p) => `preset:${p.id}` === value);
    if (!preset) return;
    update({
      device_type: "note_array",
      notes_wide: preset.notes_wide,
      notes_tall: preset.notes_tall,
      ...modeOnConvert,
    });
  };

  const handleCustomDim = (key: "notes_wide" | "notes_tall", rawValue: string) => {
    const n = Number.parseInt(rawValue, 10);
    if (!Number.isInteger(n) || n < 1 || n > MAX_NOTES_PER_AXIS) {
      setDimError(t("customRangeError", { max: MAX_NOTES_PER_AXIS }));
      return; // Block the save — never persist an invalid dimension.
    }
    setDimError(undefined);
    update({ device_type: "note_array", [key]: n });
  };

  /** A size the board's "Auto-detect from board" action read: the type and W×H it implies. */
  const handleGeometry = (geometry: ActionGeometry) => {
    if (geometry.device_type === "note_array") {
      const w = geometry.notes_wide ?? 1;
      const h = geometry.notes_tall ?? 1;
      setCustomOpen(!NOTE_ARRAY_PRESETS.some((p) => p.notes_wide === w && p.notes_tall === h));
      update({ device_type: "note_array", notes_wide: w, notes_tall: h, ...cloudOnConvert() });
    } else if (geometry.device_type === "flagship" || geometry.device_type === "note") {
      setCustomOpen(false);
      update({ device_type: geometry.device_type });
    }
  };

  const handleRemove = async () => {
    if (await displays.removeBoard(board.id)) onRemoved?.();
  };

  return (
    <Stack gap="3">
      {/* Why the backend skipped this board at startup (issue #1829) —
          verbatim reason, fixed via the form below (saving re-initializes
          the board's client). */}
      {initError && (
        <Alert variant="destructive" data-testid="board-init-error-detail">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("initError.title")}</AlertTitle>
          <AlertDescription>
            <Stack gap="1">
              <Text size="xs" className="break-words">
                {initError}
              </Text>
              <Text size="xs" tone="muted">
                {t("initError.hint")}
              </Text>
            </Stack>
          </AlertDescription>
        </Alert>
      )}

      {/* Board name (issue #1792). Trimmed on save; clearing it saves "" and
          the backend restores its default name. */}
      <BoardNameField board={board} onRename={(name) => update({ name })} />

      {/* Pause / Resume row (issue #970) */}
      <Flex
        align="center"
        justify="between"
        className={`rounded-md border px-3 py-2 ${
          isPaused ? "border-amber-500/60 bg-amber-500/10" : "border-transparent bg-muted/30"
        }`}
      >
        <Flex align="start" gap="2" className="min-w-0">
          <Pause
            className={`h-3.5 w-3.5 mt-0.5 flex-shrink-0 ${isPaused ? "text-amber-600" : "text-muted-foreground"}`}
          />
          <Box className="min-w-0">
            <Text size="xs" weight="medium">
              {isPaused ? t("pause.resumeToggle") : t("pause.toggle")}
            </Text>
            <Text tone="muted" className="text-[11px]">
              {t("pause.tooltip")}
            </Text>
          </Box>
        </Flex>
        <Switch
          checked={isPaused}
          onCheckedChange={(checked) => displays.setPaused(board.id, checked)}
          aria-label={isPaused ? t("pause.resumeToggle") : t("pause.toggle")}
          data-testid="board-pause-switch"
        />
      </Flex>

      {/* Type + Color row (a Vestaboard's or a panel's; an output plugin's
          board is sized by its device model) */}
      {!isPluginOutput && (
        <Stack gap="2">
          <Flex align="center" gap="4" wrap>
            {isVirtual ? (
              // A panel's grid is auto-fit from its TV size — the type/preset
              // picker would desync it from the panel.
              <Flex align="center" gap="2">
                <Text as="span" tone="muted" className="text-[11px]">
                  {t("typeLabel")}
                </Text>
                <Text as="span" size="xs" tone="muted">
                  {t("virtualSizeHint")}
                </Text>
              </Flex>
            ) : (
              <Flex align="center" gap="2">
                <Text as="span" tone="muted" className="text-[11px]">
                  {t("typeLabel")}
                </Text>
                <Select value={currentConfigValue()} onValueChange={(v) => v && handleConfigChange(v)}>
                  <SelectTrigger className="h-7 w-[200px] text-xs" aria-label={t("deviceTypeAriaLabel")}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectLabel>{t("deviceGroupLabel")}</SelectLabel>
                      <SelectItem value="flagship">{t("flagshipLabel")}</SelectItem>
                      <SelectItem value="note">{t("noteLabel")}</SelectItem>
                    </SelectGroup>
                    <SelectGroup>
                      <SelectLabel>{t("noteArrayGroupLabel")}</SelectLabel>
                      {NOTE_ARRAY_PRESETS.map((p) => (
                        <SelectItem key={p.id} value={`preset:${p.id}`}>
                          {t(`presets.${p.id}`)}
                        </SelectItem>
                      ))}
                      <SelectItem value="custom">{t("customLabel")}</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Flex>
            )}
            <Flex align="center" gap="2">
              <Text as="span" tone="muted" className="text-[11px]">
                {t("colorLabel")}
              </Text>
              <Flex gap="2">
                <button
                  onClick={() => update({ board_color: "black" })}
                  aria-label={t("blackAriaLabel")}
                  aria-pressed={board.board_color === "black"}
                  className={`h-6 w-6 rounded-full border-2 bg-board-surface-dark transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 ${
                    board.board_color === "black"
                      ? "border-primary ring-2 ring-primary/30"
                      : "border-border hover:border-muted-foreground"
                  }`}
                />
                <button
                  onClick={() => update({ board_color: "white" })}
                  aria-label={t("whiteAriaLabel")}
                  aria-pressed={board.board_color === "white"}
                  className={`h-6 w-6 rounded-full border-2 bg-board-surface-light transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 ${
                    board.board_color === "white"
                      ? "border-primary ring-2 ring-primary/30"
                      : "border-border hover:border-muted-foreground"
                  }`}
                />
              </Flex>
            </Flex>
            {/* Code-62 flap (issue #1657). Flagship only: Note hardware has
                only ever carried the heart, so there is nothing for its owner
                to tell us. */}
            {board.device_type === "flagship" && (
              <Flex align="center" gap="2">
                <Text as="span" tone="muted" className="text-[11px]">
                  {t("code62Label")}
                </Text>
                <Flex gap="2">
                  {CODE62_CHOICES.map(({ value, glyph, labelKey }) => {
                    const selected = (board.code62_glyph ?? "degree") === value;
                    return (
                      <button
                        key={value}
                        onClick={() => update({ code62_glyph: value })}
                        aria-label={t(labelKey)}
                        aria-pressed={selected}
                        data-testid={`board-code62-${value}`}
                        className={`flex h-6 w-6 items-center justify-center rounded-full border-2 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 ${
                          selected
                            ? "border-primary ring-2 ring-primary/30"
                            : "border-border hover:border-muted-foreground"
                        }`}
                      >
                        <Text as="span" aria-hidden="true">
                          {glyph}
                        </Text>
                      </button>
                    );
                  })}
                </Flex>
              </Flex>
            )}
          </Flex>

          {board.device_type === "flagship" && (
            <Text as="p" tone="muted" className="text-[11px]">
              {t("code62Help")}
            </Text>
          )}

          {/* Custom W×H inputs (note arrays only; never for a panel's
              auto-fit board) */}
          {!isVirtual && (customOpen || currentConfigValue() === "custom") && (
            <Stack gap="1">
              <Flex align="end" gap="2">
                <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
                  {t("notesWideLabel")}
                  <input
                    type="number"
                    min={1}
                    max={MAX_NOTES_PER_AXIS}
                    value={board.notes_wide ?? 1}
                    onChange={(e) => handleCustomDim("notes_wide", e.target.value)}
                    className="h-8 w-16 px-2 text-xs rounded-md border bg-background"
                  />
                </label>
                <Text as="span" size="xs" tone="muted" className="pb-1.5">
                  ×
                </Text>
                <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
                  {t("notesTallLabel")}
                  <input
                    type="number"
                    min={1}
                    max={MAX_NOTES_PER_AXIS}
                    value={board.notes_tall ?? 1}
                    onChange={(e) => handleCustomDim("notes_tall", e.target.value)}
                    className="h-8 w-16 px-2 text-xs rounded-md border bg-background"
                  />
                </label>
              </Flex>
              {dimError && (
                <Text role="alert" tone="destructive" className="text-[10px]">
                  {dimError}
                </Text>
              )}
            </Stack>
          )}
        </Stack>
      )}

      {/* Connection section: the output's own settings screen, drawn from its
          manifest (plan D13) — a Vestaboard's included. Virtual boards render
          to memory: offering credentials here is what made panels read as
          "needing API credentials". */}
      <Box className="border-t pt-3">
        {isVirtual ? (
          <Flex align="start" gap="2" data-testid="virtual-board-hint">
            <Tv className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-muted-foreground" />
            <Text size="xs" tone="muted">
              {panelName ? t("virtualConnectionHintNamed", { name: panelName }) : t("virtualConnectionHint")}
            </Text>
          </Flex>
        ) : (
          <OutputBoardSettings
            key={board.id}
            board={board}
            saving={displays.saving}
            onSave={(outputConfig) => update({ output_config: outputConfig })}
            onGeometry={isPluginOutput ? undefined : handleGeometry}
          />
        )}
      </Box>

      {/* Remove board - bottom. A virtual board still referenced by a panel is
          removed by deleting the panel, not here — pulling it out from under a
          live panel blanks the TV. */}
      <Box className="border-t pt-2">
        <Button
          variant="ghost"
          size="sm"
          className="text-[11px] text-muted-foreground hover:text-destructive h-7 px-2"
          onClick={() => void handleRemove()}
          disabled={boards.length <= 1 || (isVirtual && panelName !== undefined)}
          title={isVirtual && panelName !== undefined ? t("virtualRemoveHint") : undefined}
        >
          <Trash2 className="h-3 w-3 mr-1" />
          {t("removeBoard")}
        </Button>
        {isVirtual && panelName !== undefined && (
          <Text as="p" tone="muted" className="mt-1 text-[10px]">
            {t("virtualRemoveHint")}
          </Text>
        )}
      </Box>
    </Stack>
  );
}

/** The Vestaboard shapes "Add a display" offers: each adds that board at once. */
export function VestaboardTypeButtons({
  onAdd,
  disabled,
}: {
  onAdd: (deviceType: DeviceType) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("displaySettings");
  return (
    <Stack gap="2">
      <Text as="span" size="xs" tone="muted">
        {t("selectType")}
      </Text>
      <Flex align="center" gap="2" wrap>
        <Button variant="outline" size="sm" className="text-xs" disabled={disabled} onClick={() => onAdd("flagship")}>
          <Monitor className="h-3 w-3 mr-1" />
          {t("flagshipLabel")}
        </Button>
        <Button variant="outline" size="sm" className="text-xs" disabled={disabled} onClick={() => onAdd("note")}>
          <Smartphone className="h-3 w-3 mr-1" />
          {t("noteLabel")}
        </Button>
        <Button variant="outline" size="sm" className="text-xs" disabled={disabled} onClick={() => onAdd("note_array")}>
          <LayoutGrid className="h-3 w-3 mr-1" />
          {t("noteArrayLabel")}
        </Button>
      </Flex>
    </Stack>
  );
}
