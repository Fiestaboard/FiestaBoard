"use client";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge as BadgeUI,
  Box,
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Flex,
  Grid,
  Label,
  PageSection,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Stack,
  Switch,
  Text,
  TextLink,
  ToggleCard,
  ToggleCardGroup,
} from "@fiestaboard/ui";
import { SecretInput } from "@fiestaboard/ui/components/forms/secret-input";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  Key,
  KeyRound,
  LayoutGrid,
  Loader2,
  Monitor,
  Pause,
  Plus,
  Smartphone,
  Trash2,
  Tv,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { BoardSizeIndicator } from "@/components/board-size-indicator";
import { queryKeys, useBoardSettings, useStatus } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type { BoardInstance, Code62Glyph, DeviceType } from "@/lib/api";
import { api } from "@/lib/api";
import { isNoteArray, MAX_BOARD_NAME_LENGTH, MAX_NOTES_PER_AXIS, NOTE_ARRAY_PRESETS } from "@/lib/board-dimensions";

import { TileGridAssignment } from "./tile-grid-assignment";

/**
 * The two flaps a Flagship's character-code-62 slot can physically carry
 * (issue #1657). Module scope so the swatch pair below has one source of truth
 * and a stable identity across renders.
 */
const CODE62_CHOICES: ReadonlyArray<{ value: Code62Glyph; glyph: string; labelKey: string }> = [
  { value: "degree", glyph: "°", labelKey: "code62DegreeAriaLabel" },
  { value: "heart", glyph: "♥", labelKey: "code62HeartAriaLabel" },
];

/** How a board is driven: the Vestaboard Local API, or the Cloud (RW) API. */
type ApiMode = "local" | "cloud";

function isApiMode(value: string): value is ApiMode {
  return value === "local" || value === "cloud";
}

/**
 * Tiles usable for the board's CURRENT W×H — mirrors the backend's
 * BoardInstance.configured_tiles(): in-range, enabled, host + key present.
 * (Out-of-range entries are kept server-side but don't count.)
 */
function countAssignedTiles(board: BoardInstance): number {
  const notesWide = board.notes_wide ?? 1;
  const notesTall = board.notes_tall ?? 1;
  return (board.tiles ?? []).filter(
    (tile) =>
      tile.row < notesTall &&
      tile.col < notesWide &&
      (tile.enabled ?? true) &&
      Boolean(tile.host) &&
      Boolean(tile.local_api_key),
  ).length;
}

/**
 * Whether a note array is actually driven tile-by-tile — mirrors the
 * backend's BoardInstance.uses_local_tiles: local mode AND at least one saved
 * tile. A token-only array whose api_mode says "local" (e.g. just switched in
 * the UI, or a legacy dict) still drives via its Cloud token.
 */
function usesLocalTiles(board: BoardInstance): boolean {
  return (board.api_mode ?? "cloud") === "local" && (board.tiles?.length ?? 0) > 0;
}

/** Connection-configured rule for note arrays — mirrors BoardInstance.is_connection_configured. */
function isArrayConfigured(board: BoardInstance): boolean {
  if (usesLocalTiles(board)) return countAssignedTiles(board) > 0;
  return board.note_array_token === "***" || Boolean(board.note_array_token);
}

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

function BoardConnectionForm({
  board,
  onUpdate,
}: {
  board: BoardInstance;
  onUpdate: (boardId: string, updates: Partial<BoardInstance>) => void;
}) {
  const t = useTranslations("displaySettings");
  const [localKeyMode, setLocalKeyMode] = useState<"api_key" | "enablement_token">("api_key");
  const [enablementToken, setEnablementToken] = useState("");
  const [isEnabling, setIsEnabling] = useState(false);

  // Note arrays default to cloud mode (the token path); switching to local
  // swaps the token field for the per-tile assignment grid.
  const isArray = isNoteArray(board.device_type);
  const apiMode = board.api_mode ?? (isArray ? "cloud" : "local");
  const hasLocalKey = board.local_api_key === "***" || (board.local_api_key && board.local_api_key.length > 0);
  const hasCloudKey = board.cloud_key === "***" || (board.cloud_key && board.cloud_key.length > 0);
  const hasNoteArrayToken = board.note_array_token === "***" || Boolean(board.note_array_token);
  const hasHost = board.host && board.host.length > 0;

  // Mirrors the backend's BoardInstance.is_connection_configured: an array
  // with saved local tiles needs at least one usable tile; otherwise (cloud,
  // or local mode without tiles yet) it falls back to the Cloud token.
  // Virtual boards (FiestaPanel) render to memory and are always reachable.
  const isConfigured =
    apiMode === "virtual"
      ? true
      : isArray
        ? isArrayConfigured(board)
        : (apiMode === "local" && hasLocalKey && hasHost) || (apiMode === "cloud" && hasCloudKey);

  const handleEnableLocalApi = async () => {
    if (!board.host || !enablementToken) {
      toast.error(t("boardHostAndTokenRequired"));
      return;
    }
    setIsEnabling(true);
    try {
      const result = await api.enableLocalApi({
        host: board.host,
        enablement_token: enablementToken,
      });
      if (result.success && result.api_key) {
        onUpdate(board.id, { local_api_key: result.api_key });
        setEnablementToken("");
        setLocalKeyMode("api_key");
        toast.success(t("localApiEnabled"));
      } else {
        toast.error(result.message || t("failedToEnable"));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("failedToEnable"));
    } finally {
      setIsEnabling(false);
    }
  };

  return (
    <Stack gap="3">
      <Flex align="center" justify="between">
        <Label className="text-xs font-medium">{t("connectionLabel")}</Label>
        {isConfigured ? (
          <BadgeUI variant="default" className="text-[10px] h-5 bg-board-green">
            <Check className="h-2.5 w-2.5 mr-0.5" />
            {t("connected")}
          </BadgeUI>
        ) : (
          <BadgeUI variant="destructive" className="text-[10px] h-5">
            <AlertCircle className="h-2.5 w-2.5 mr-0.5" />
            {t("notConfigured")}
          </BadgeUI>
        )}
      </Flex>

      {/* API Mode */}
      {/* One-of-two, so a radiogroup: one tab stop for the pair, arrows move
          the choice, and each tile announces its position in the set. */}
      <ToggleCardGroup
        columns="2"
        size="sm"
        value={apiMode}
        onValueChange={(value) => {
          if (isApiMode(value)) onUpdate(board.id, { api_mode: value });
        }}
        aria-label={t("apiModeLabel")}
      >
        <ToggleCard value="local" title={t("localApiLabel")} description={t("localApiDescription")} />
        <ToggleCard value="cloud" title={t("cloudApiLabel")} description={t("cloudApiDescription")} />
      </ToggleCardGroup>

      {/* Local array mode: per-tile assignment grid instead of host/key fields */}
      {isArray && apiMode === "local" && <TileGridAssignment board={board} onUpdate={onUpdate} />}

      {/* Local API Fields (single boards) */}
      {apiMode === "local" && !isArray && (
        <>
          <Stack gap="1">
            <label className="text-xs font-medium">
              {t("boardHostLabel")}{" "}
              <Text as="span" size="xs" tone="destructive">
                *
              </Text>
            </label>
            <input
              type="text"
              defaultValue={board.host ?? ""}
              onBlur={(e) => {
                if (e.target.value !== board.host) {
                  onUpdate(board.id, { host: e.target.value });
                }
              }}
              placeholder={t("boardHostPlaceholder")}
              className="w-full h-8 px-2 text-xs rounded-md border bg-background font-mono"
            />
          </Stack>

          {/* Auth method toggle */}
          <Grid cols="2" gap="2">
            <button
              type="button"
              onClick={() => setLocalKeyMode("api_key")}
              className={`flex items-center justify-center gap-1 p-1.5 rounded-md border text-[10px] transition-colors ${
                localKeyMode === "api_key"
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-muted hover:border-primary/50 text-muted-foreground"
              }`}
            >
              <Key className="h-3 w-3" />
              {t("apiKeyLabel")}
            </button>
            <button
              type="button"
              onClick={() => setLocalKeyMode("enablement_token")}
              className={`flex items-center justify-center gap-1 p-1.5 rounded-md border text-[10px] transition-colors ${
                localKeyMode === "enablement_token"
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-muted hover:border-primary/50 text-muted-foreground"
              }`}
            >
              <KeyRound className="h-3 w-3" />
              {t("enablementTokenLabel")}
            </button>
          </Grid>

          {localKeyMode === "api_key" ? (
            <Stack gap="1">
              <label className="text-xs font-medium" htmlFor={`local-api-key-${board.id}`}>
                {t("localApiKeyLabel")}{" "}
                <Text as="span" size="xs" tone="destructive">
                  *
                </Text>
              </label>
              <SecretInput
                id={`local-api-key-${board.id}`}
                defaultValue={board.local_api_key === "***" ? "" : (board.local_api_key ?? "")}
                onBlur={(e) => {
                  const val = e.target.value;
                  if (val && val !== "***" && val !== board.local_api_key) {
                    onUpdate(board.id, { local_api_key: val });
                  }
                }}
                placeholder={hasLocalKey ? t("localApiKeySetPlaceholder") : t("localApiKeyPlaceholder")}
                revealDisabled={board.local_api_key === "***"}
                showLabel={t("showSecretAriaLabel")}
                hideLabel={t("hideSecretAriaLabel")}
                className="h-8 pl-2 text-xs"
              />
              <Text tone="muted" className="text-[10px]">
                {t.rich("localApiKeyHelp", {
                  link: (chunks) => (
                    <TextLink
                      href="https://fiestaboard.app/docs/setup/api-keys"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline"
                    >
                      {chunks}
                    </TextLink>
                  ),
                })}
              </Text>
            </Stack>
          ) : (
            <Stack gap="1.5">
              <label className="text-xs font-medium" htmlFor={`enablement-token-${board.id}`}>
                {t("enablementTokenLabel")}
              </label>
              <SecretInput
                id={`enablement-token-${board.id}`}
                value={enablementToken}
                onChange={(e) => setEnablementToken(e.target.value)}
                placeholder={t("enablementTokenPlaceholder")}
                showLabel={t("showSecretAriaLabel")}
                hideLabel={t("hideSecretAriaLabel")}
                className="h-8 pl-2 text-xs"
              />
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={handleEnableLocalApi}
                disabled={!board.host || !enablementToken || isEnabling}
                className="w-full text-xs"
              >
                {isEnabling ? (
                  <>
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                    {t("enabling")}
                  </>
                ) : (
                  t("getApiKeyFromBoard")
                )}
              </Button>
            </Stack>
          )}
        </>
      )}

      {/* Cloud API Fields (single boards — arrays use the token below) */}
      {apiMode === "cloud" && !isArray && (
        <Stack gap="1">
          <label className="text-xs font-medium" htmlFor={`cloud-key-${board.id}`}>
            {t("cloudKeyLabel")}{" "}
            <Text as="span" size="xs" tone="destructive">
              *
            </Text>
          </label>
          <SecretInput
            id={`cloud-key-${board.id}`}
            defaultValue={board.cloud_key === "***" ? "" : (board.cloud_key ?? "")}
            onBlur={(e) => {
              const val = e.target.value;
              if (val && val !== "***" && val !== board.cloud_key) {
                onUpdate(board.id, { cloud_key: val });
              }
            }}
            placeholder={hasCloudKey ? t("cloudKeySetPlaceholder") : t("cloudKeyPlaceholder")}
            revealDisabled={board.cloud_key === "***"}
            showLabel={t("showSecretAriaLabel")}
            hideLabel={t("hideSecretAriaLabel")}
            className="h-8 pl-2 text-xs"
          />
          <Text tone="muted" className="text-[10px]">
            {t("cloudKeyHelp")}
          </Text>
        </Stack>
      )}

      {/* Note-array Cloud API token (X-Vestaboard-Token) */}
      {isArray && apiMode === "cloud" && (
        <Stack gap="1">
          <label className="text-xs font-medium" htmlFor={`note-array-token-${board.id}`}>
            {t("noteArrayTokenLabel")}
          </label>
          <SecretInput
            id={`note-array-token-${board.id}`}
            defaultValue={board.note_array_token === "***" ? "" : (board.note_array_token ?? "")}
            onBlur={(e) => {
              const val = e.target.value;
              if (val && val !== "***" && val !== board.note_array_token) {
                onUpdate(board.id, { note_array_token: val });
              }
            }}
            placeholder={hasNoteArrayToken ? t("noteArrayTokenSetPlaceholder") : t("noteArrayTokenPlaceholder")}
            revealDisabled={board.note_array_token === "***"}
            showLabel={t("showSecretAriaLabel")}
            hideLabel={t("hideSecretAriaLabel")}
            className="h-8 pl-2 text-xs"
          />
          <Text tone="muted" className="text-[10px]">
            {t("noteArrayTokenHelp")}
          </Text>
        </Stack>
      )}

      {/* Validation message */}
      {!isConfigured && (
        <Flex align="center" gap="1.5" className="p-1.5 rounded-md bg-destructive/10 text-foreground text-[10px]">
          <AlertCircle className="h-3 w-3 flex-shrink-0" />
          <Text as="span" className="text-[10px]">
            {isArray
              ? apiMode === "local"
                ? t("tileGrid.assignRequired")
                : t("noteArrayTokenRequired")
              : apiMode === "local"
                ? t("localApiRequired")
                : t("cloudApiRequired")}
          </Text>
        </Flex>
      )}
    </Stack>
  );
}

export function DisplaySettings() {
  const t = useTranslations("displaySettings");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const { data: boardSettings, isLoading } = useBoardSettings();
  // Per-board init errors from the shared 15s status poll (issue #1829):
  // a board the backend skipped at startup (issue #1749) carries the reason
  // in `boards[<id>].error`, surfaced on its card below.
  const { data: statusData } = useStatus();
  const [showTypePicker, setShowTypePicker] = useState(false);
  // Per-board UI state for the note-array selector / custom inputs / auto-detect.
  const [customOpen, setCustomOpen] = useState<Record<string, boolean>>({});
  const [dimError, setDimError] = useState<Record<string, string | undefined>>({});
  const [detectingBoardId, setDetectingBoardId] = useState<string | null>(null);
  const [detectError, setDetectError] = useState<Record<string, string | undefined>>({});
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
    queryClient.invalidateQueries({ queryKey: ["all-settings"] });
    // Board count and device type affect template rendering dimensions
    // and which board previews are shown, so refresh previews and displays.
    queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
    queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
  };

  const updateMutation = useMutation({
    mutationFn: (updates: { board_type?: "black" | "white" | null; boards?: BoardInstance[] }) =>
      api.updateBoardSettings(updates),
    onSuccess: () => {
      invalidate();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const addMutation = useMutation({
    mutationFn: (board: Partial<BoardInstance> & { device_type: DeviceType }) => api.addBoard(board),
    onSuccess: () => {
      invalidate();
      toast.success(t("boardAdded"));
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (boardId: string) => api.removeBoard(boardId),
    onSuccess: () => {
      invalidate();
      // The per-board init errors ride the 15s ["status"] poll — refetch it
      // now so deleting a failed board doesn't leave a ghost error banner
      // until the next poll tick (#1829 review).
      queryClient.invalidateQueries({ queryKey: ["status"] });
      toast.success(t("boardRemoved"));
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const boards = boardSettings?.boards ?? [];

  // Panels, to recognize which virtual board backs which FiestaPanel: its
  // card must not offer credentials, and removing it out from under a live
  // panel (blanking the TV) is blocked — the panel editor owns that board.
  const { data: panelsData } = useQuery({
    queryKey: ["panels"],
    queryFn: () => api.listPanels(),
  });
  const panelNameByBoardId = new Map((panelsData?.panels ?? []).map((p) => [p.board_id, p.name]));

  const handleAddBoard = (deviceType: DeviceType) => {
    if (deviceType === "note_array") {
      // Arrays start as the smallest real layout (the "2 side-by-side"
      // preset) in cloud mode — they're driven via the Cloud API today.
      addMutation.mutate({ device_type: "note_array", notes_wide: 2, notes_tall: 1, api_mode: "cloud" });
    } else {
      addMutation.mutate({ device_type: deviceType });
    }
    setShowTypePicker(false);
  };

  const handleRemoveBoard = (boardId: string) => {
    if (boards.length <= 1) {
      toast.error(t("atLeastOneBoard"));
      return;
    }
    removeMutation.mutate(boardId);
  };

  const handleUpdateBoard = (boardId: string, updates: Partial<BoardInstance>) => {
    const updated = boards.map((b) => (b.id === boardId ? { ...b, ...updates } : b));
    updateMutation.mutate({ boards: updated });
  };

  // Map a board to the synthetic Select value. Note arrays whose dims match a
  // preset resolve to that preset; otherwise to "custom". (Match by dimensions,
  // never by the detect endpoint's `matched_preset` label string.)
  const currentConfigValue = (board: BoardInstance): string => {
    if (board.device_type !== "note_array") return board.device_type; // "flagship" | "note"
    const match = NOTE_ARRAY_PRESETS.find(
      (p) => p.notes_wide === (board.notes_wide ?? 1) && p.notes_tall === (board.notes_tall ?? 1),
    );
    return match ? `preset:${match.id}` : "custom";
  };

  const handleConfigChange = (board: BoardInstance, value: string) => {
    if (value === "flagship" || value === "note") {
      setCustomOpen((prev) => ({ ...prev, [board.id]: false }));
      handleUpdateBoard(board.id, { device_type: value });
      return;
    }
    // Converting a single board (whose api_mode defaults to "local") into an
    // array must land in cloud mode — the array default. An existing array
    // keeps whatever mode the user picked; only its size changes.
    const modeOnConvert = board.device_type !== "note_array" ? { api_mode: "cloud" as const } : {};
    if (value === "custom") {
      setCustomOpen((prev) => ({ ...prev, [board.id]: true }));
      const w = board.device_type === "note_array" ? (board.notes_wide ?? 1) : 1;
      const h = board.device_type === "note_array" ? (board.notes_tall ?? 1) : 1;
      handleUpdateBoard(board.id, { device_type: "note_array", notes_wide: w, notes_tall: h, ...modeOnConvert });
      return;
    }
    // value === "preset:<id>"
    setCustomOpen((prev) => ({ ...prev, [board.id]: false }));
    const preset = NOTE_ARRAY_PRESETS.find((p) => `preset:${p.id}` === value);
    if (!preset) return;
    handleUpdateBoard(board.id, {
      device_type: "note_array",
      notes_wide: preset.notes_wide,
      notes_tall: preset.notes_tall,
      ...modeOnConvert,
    });
  };

  const handleCustomDim = (board: BoardInstance, key: "notes_wide" | "notes_tall", rawValue: string) => {
    const n = Number.parseInt(rawValue, 10);
    if (!Number.isInteger(n) || n < 1 || n > MAX_NOTES_PER_AXIS) {
      setDimError((prev) => ({ ...prev, [board.id]: t("customRangeError", { max: MAX_NOTES_PER_AXIS }) }));
      return; // Block the save — never persist an invalid dimension.
    }
    setDimError((prev) => ({ ...prev, [board.id]: undefined }));
    handleUpdateBoard(board.id, { device_type: "note_array", [key]: n });
  };

  const handleAutoDetect = async (board: BoardInstance) => {
    setDetectingBoardId(board.id);
    setDetectError((prev) => ({ ...prev, [board.id]: undefined }));
    try {
      const res = await api.detectBoardSize(board.id);
      if (res.device_type === "note_array") {
        const w = res.notes_wide ?? 1;
        const h = res.notes_tall ?? 1;
        const isPreset = NOTE_ARRAY_PRESETS.some((p) => p.notes_wide === w && p.notes_tall === h);
        setCustomOpen((prev) => ({ ...prev, [board.id]: !isPreset }));
        handleUpdateBoard(board.id, {
          device_type: "note_array",
          notes_wide: w,
          notes_tall: h,
          // Converting a non-array board lands in cloud mode (array default).
          ...(board.device_type !== "note_array" ? { api_mode: "cloud" as const } : {}),
        });
      } else {
        setCustomOpen((prev) => ({ ...prev, [board.id]: false }));
        handleUpdateBoard(board.id, { device_type: res.device_type });
      }
    } catch (err) {
      setDetectError((prev) => ({
        ...prev,
        [board.id]: err instanceof Error ? err.message : t("detectFailed"),
      }));
    } finally {
      setDetectingBoardId(null);
    }
  };

  const pauseMutation = useMutation({
    mutationFn: ({ boardId, paused }: { boardId: string; paused: boolean }) => api.setBoardPaused(boardId, paused),
    onSuccess: () => {
      invalidate();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const handleTogglePaused = (boardId: string, paused: boolean) => {
    pauseMutation.mutate({ boardId, paused });
  };

  if (isLoading) {
    return (
      <PageSection>
        <Skeleton className="h-5 w-32" />
        <Skeleton className="mt-2 h-4 w-48" />
        <Skeleton className="mt-4 h-20 w-full" />
      </PageSection>
    );
  }

  return (
    <PageSection icon={<Monitor />} title={t("title")} description={t("description")} contentClassName="space-y-4">
      <Stack gap="3">
        {boards.map((board) => {
          const isPaused = board.paused === true;
          const apiMode = board.api_mode ?? "local";
          // Virtual boards (FiestaPanel) render to memory: there is no
          // connection to configure, so they are never "Not configured"
          // and none of the credential/type controls apply (issue: a
          // freshly created panel showed as needing API credentials).
          const isVirtual = apiMode === "virtual";
          const panelName = isVirtual ? panelNameByBoardId.get(board.id) : undefined;
          const hasLocalKey = board.local_api_key === "***" || Boolean(board.local_api_key);
          const hasCloudKey = board.cloud_key === "***" || Boolean(board.cloud_key);
          const hasHost = Boolean(board.host);
          // Same rule as BoardConnectionForm: arrays with saved local tiles
          // connect via assigned tiles, token-only arrays via the Cloud
          // token (even in local mode — the backend's cloud fallback),
          // flagship/note via the selected API mode's credentials.
          const isConnected = isVirtual
            ? true
            : isNoteArray(board.device_type)
              ? isArrayConfigured(board)
              : (apiMode === "local" && hasLocalKey && hasHost) || (apiMode === "cloud" && hasCloudKey);
          // Why this board has no client, when the backend skipped it at
          // startup (issues #1749/#1829). Verbatim backend reason string.
          const initError = statusData?.boards?.[board.id]?.error ?? null;

          return (
            <Collapsible
              key={board.id}
              data-testid="board-card"
              data-paused={isPaused ? "true" : undefined}
              className={`rounded-lg border overflow-hidden ${isPaused ? "border-amber-500/60 bg-amber-500/5" : ""}`}
            >
              <CollapsibleTrigger className="flex items-center gap-3 p-3 w-full text-left hover:bg-muted/40 transition-colors [&[data-state=open]>div:first-child>svg:first-child]:hidden [&[data-state=closed]>div:first-child>svg:last-child]:hidden">
                <Box className="flex-shrink-0 text-muted-foreground">
                  <ChevronRight className="h-4 w-4" />
                  <ChevronDown className="h-4 w-4" />
                </Box>
                <Box className="flex-1 min-w-0">
                  <Text weight="medium" className="truncate">
                    {board.name || t("unnamedBoard")}
                  </Text>
                  <Flex align="center" gap="2" className="text-xs text-muted-foreground">
                    <Text as="span" size="xs" className="capitalize">
                      {board.device_type}
                    </Text>
                    <Text as="span" size="xs" tone="muted">
                      •
                    </Text>
                    <BoardSizeIndicator
                      deviceType={board.device_type}
                      notesWide={board.notes_wide}
                      notesTall={board.notes_tall}
                    />
                    <Text as="span" size="xs" tone="muted">
                      •
                    </Text>
                    <Box
                      className="h-3 w-3 rounded border"
                      style={{
                        backgroundColor:
                          board.board_color === "white"
                            ? "var(--color-board-surface-light)"
                            : "var(--color-board-surface-dark)",
                      }}
                    />
                  </Flex>
                </Box>
                <Flex align="center" gap="1.5" className="flex-shrink-0">
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
                  {isPaused && (
                    <BadgeUI
                      variant="default"
                      className="text-[10px] h-5 bg-amber-500 text-white"
                      data-testid="board-paused-badge"
                      title={t("pause.tooltip")}
                    >
                      <Pause className="h-2.5 w-2.5 mr-0.5" />
                      {t("pause.badge")}
                    </BadgeUI>
                  )}
                  {isVirtual ? (
                    <BadgeUI variant="secondary" className="text-[10px] h-5" data-testid="board-virtual-badge">
                      <Tv className="h-2.5 w-2.5 mr-0.5" />
                      {t("virtualBadge")}
                    </BadgeUI>
                  ) : isConnected ? (
                    <BadgeUI variant="default" className="text-[10px] h-5 bg-board-green">
                      <Check className="h-2.5 w-2.5 mr-0.5" />
                      {t("connected")}
                    </BadgeUI>
                  ) : (
                    <BadgeUI variant="destructive" className="text-[10px] h-5">
                      <AlertCircle className="h-2.5 w-2.5 mr-0.5" />
                      {t("notConfigured")}
                    </BadgeUI>
                  )}
                </Flex>
              </CollapsibleTrigger>

              <CollapsibleContent>
                <Stack gap="3" className="border-t px-4 pb-4 pt-3">
                  {/* Why the backend skipped this board at startup (issue
                      #1829) — verbatim reason, fixed via the form below
                      (saving re-initializes the board's client). */}
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

                  {/* Board name (issue #1792). Trimmed on save; clearing it
                      saves "" and the backend restores its default name. */}
                  <BoardNameField board={board} onRename={(name) => handleUpdateBoard(board.id, { name })} />

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
                        className={`h-3.5 w-3.5 mt-0.5 flex-shrink-0 ${
                          isPaused ? "text-amber-600" : "text-muted-foreground"
                        }`}
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
                      onCheckedChange={(checked) => handleTogglePaused(board.id, checked)}
                      aria-label={isPaused ? t("pause.resumeToggle") : t("pause.toggle")}
                      data-testid="board-pause-switch"
                    />
                  </Flex>

                  {/* Type + Color row */}
                  <Stack gap="2">
                    <Flex align="center" gap="4" wrap>
                      {isVirtual ? (
                        // A panel's grid is auto-fit from its TV size — the
                        // type/preset picker would desync it from the panel.
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
                          <Select value={currentConfigValue(board)} onValueChange={(v) => handleConfigChange(board, v)}>
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
                            onClick={() => handleUpdateBoard(board.id, { board_color: "black" })}
                            aria-label={t("blackAriaLabel")}
                            aria-pressed={board.board_color === "black"}
                            className={`h-6 w-6 rounded-full border-2 bg-board-surface-dark transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 ${
                              board.board_color === "black"
                                ? "border-primary ring-2 ring-primary/30"
                                : "border-border hover:border-muted-foreground"
                            }`}
                          />
                          <button
                            onClick={() => handleUpdateBoard(board.id, { board_color: "white" })}
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
                      {/* Code-62 flap (issue #1657). Flagship only: Note
                          hardware has only ever carried the heart, so there
                          is nothing for its owner to tell us. */}
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
                                  onClick={() => handleUpdateBoard(board.id, { code62_glyph: value })}
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

                    {/* Custom W×H inputs (note arrays only; never for a
                        panel's auto-fit board) */}
                    {!isVirtual && (customOpen[board.id] || currentConfigValue(board) === "custom") && (
                      <Stack gap="1">
                        <Flex align="end" gap="2">
                          <label className="flex flex-col gap-1 text-[11px] text-muted-foreground">
                            {t("notesWideLabel")}
                            <input
                              type="number"
                              min={1}
                              max={MAX_NOTES_PER_AXIS}
                              value={board.notes_wide ?? 1}
                              onChange={(e) => handleCustomDim(board, "notes_wide", e.target.value)}
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
                              onChange={(e) => handleCustomDim(board, "notes_tall", e.target.value)}
                              className="h-8 w-16 px-2 text-xs rounded-md border bg-background"
                            />
                          </label>
                        </Flex>
                        {dimError[board.id] && (
                          <Text role="alert" tone="destructive" className="text-[10px]">
                            {dimError[board.id]}
                          </Text>
                        )}
                      </Stack>
                    )}

                    {/* Auto-detect from board — not offered for local-mode
                        arrays: their shape is defined by assigning tiles, so
                        a local read could only echo the configured W×H back.
                        Detection is meaningful via the Cloud API (which
                        knows the array's real shape) and for single boards.
                        Virtual boards have nothing to detect. */}
                    {!isVirtual && !(isNoteArray(board.device_type) && (board.api_mode ?? "cloud") === "local") && (
                      <Stack gap="1">
                        <Button
                          type="button"
                          variant="secondary"
                          size="sm"
                          className="h-7 text-[11px]"
                          disabled={detectingBoardId === board.id}
                          onClick={() => handleAutoDetect(board)}
                        >
                          {detectingBoardId === board.id ? (
                            <>
                              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                              {t("detecting")}
                            </>
                          ) : (
                            t("autoDetect")
                          )}
                        </Button>
                        {detectError[board.id] && (
                          <Flex role="alert" align="center" gap="1.5" className="text-destructive text-[10px]">
                            <AlertCircle className="h-3 w-3 flex-shrink-0" />
                            <Text as="span" tone="destructive" className="text-[10px]">
                              {detectError[board.id]}
                            </Text>
                          </Flex>
                        )}
                      </Stack>
                    )}
                  </Stack>

                  {/* Connection section. Virtual boards render to memory:
                      offering the Local/Cloud credentials form here is what
                      made panels read as "needing API credentials", and
                      switching the mode would silently break the panel. */}
                  <Box className="border-t pt-3">
                    {isVirtual ? (
                      <Flex align="start" gap="2" data-testid="virtual-board-hint">
                        <Tv className="h-3.5 w-3.5 mt-0.5 flex-shrink-0 text-muted-foreground" />
                        <Text size="xs" tone="muted">
                          {panelName
                            ? t("virtualConnectionHintNamed", { name: panelName })
                            : t("virtualConnectionHint")}
                        </Text>
                      </Flex>
                    ) : (
                      <BoardConnectionForm board={board} onUpdate={handleUpdateBoard} />
                    )}
                  </Box>

                  {/* Remove board - bottom. A virtual board still referenced
                      by a panel is removed by deleting the panel, not here —
                      pulling it out from under a live panel blanks the TV. */}
                  <Box className="border-t pt-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-[11px] text-muted-foreground hover:text-destructive h-7 px-2"
                      onClick={() => handleRemoveBoard(board.id)}
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
              </CollapsibleContent>
            </Collapsible>
          );
        })}
      </Stack>

      {/* Add Board */}
      <Box className="pt-2">
        {!showTypePicker ? (
          <Button variant="outline" size="sm" className="text-xs" onClick={() => setShowTypePicker(true)}>
            <Plus className="h-3 w-3 mr-1" />
            {t("addBoard")}
          </Button>
        ) : (
          <Flex align="center" gap="2">
            <Text as="span" size="xs" tone="muted">
              {t("selectType")}
            </Text>
            <Button variant="outline" size="sm" className="text-xs" onClick={() => handleAddBoard("flagship")}>
              <Monitor className="h-3 w-3 mr-1" />
              {t("flagshipLabel")}
            </Button>
            <Button variant="outline" size="sm" className="text-xs" onClick={() => handleAddBoard("note")}>
              <Smartphone className="h-3 w-3 mr-1" />
              {t("noteLabel")}
            </Button>
            <Button variant="outline" size="sm" className="text-xs" onClick={() => handleAddBoard("note_array")}>
              <LayoutGrid className="h-3 w-3 mr-1" />
              {t("noteArrayLabel")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-muted-foreground"
              onClick={() => setShowTypePicker(false)}
            >
              {tCommon("cancel")}
            </Button>
          </Flex>
        )}
      </Box>
    </PageSection>
  );
}
