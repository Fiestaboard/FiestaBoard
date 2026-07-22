"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  Key,
  KeyRound,
  LayoutGrid,
  Loader2,
  Monitor,
  Pause,
  Plus,
  Smartphone,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { BoardSizeIndicator } from "@/components/board-size-indicator";
import { Badge as BadgeUI } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { queryKeys, useBoardSettings } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type { BoardInstance, DeviceType } from "@/lib/api";
import { api } from "@/lib/api";
import { isNoteArray, MAX_NOTES_PER_AXIS, NOTE_ARRAY_PRESETS } from "@/lib/board-dimensions";

import { TileGridAssignment } from "./tile-grid-assignment";

/** Tiles usable for the board's CURRENT W×H (out-of-range entries are kept server-side but don't count). */
function countAssignedTiles(board: BoardInstance): number {
  const notesWide = board.notes_wide ?? 1;
  const notesTall = board.notes_tall ?? 1;
  return (board.tiles ?? []).filter(
    (tile) => tile.row < notesTall && tile.col < notesWide && Boolean(tile.host) && Boolean(tile.local_api_key),
  ).length;
}

function BoardConnectionForm({
  board,
  onUpdate,
}: {
  board: BoardInstance;
  onUpdate: (boardId: string, updates: Partial<BoardInstance>) => void;
}) {
  const t = useTranslations("displaySettings");
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
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

  // Mirrors the backend's BoardInstance.is_connection_configured: a cloud
  // array needs its token; a local array needs at least one assigned tile.
  const isConfigured = isArray
    ? apiMode === "local"
      ? countAssignedTiles(board) > 0
      : hasNoteArrayToken
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
    <div className="space-y-3">
      <div className="flex items-center justify-between">
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
      </div>

      {/* API Mode */}
      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={() => onUpdate(board.id, { api_mode: "local" })}
          aria-pressed={apiMode === "local"}
          className={`p-2 rounded-md border text-left transition-colors ${
            apiMode === "local" ? "border-primary bg-primary/10" : "border-muted hover:border-primary/50"
          }`}
        >
          <div className="text-xs font-medium">{t("localApiLabel")}</div>
          <div className="text-[10px] text-muted-foreground">{t("localApiDescription")}</div>
        </button>
        <button
          onClick={() => onUpdate(board.id, { api_mode: "cloud" })}
          aria-pressed={apiMode === "cloud"}
          className={`p-2 rounded-md border text-left transition-colors ${
            apiMode === "cloud" ? "border-primary bg-primary/10" : "border-muted hover:border-primary/50"
          }`}
        >
          <div className="text-xs font-medium">{t("cloudApiLabel")}</div>
          <div className="text-[10px] text-muted-foreground">{t("cloudApiDescription")}</div>
        </button>
      </div>

      {/* Local array mode: per-tile assignment grid instead of host/key fields */}
      {isArray && apiMode === "local" && <TileGridAssignment board={board} onUpdate={onUpdate} />}

      {/* Local API Fields (single boards) */}
      {apiMode === "local" && !isArray && (
        <>
          <div className="space-y-1">
            <label className="text-xs font-medium">
              {t("boardHostLabel")} <span className="text-destructive">*</span>
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
          </div>

          {/* Auth method toggle */}
          <div className="grid grid-cols-2 gap-2">
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
          </div>

          {localKeyMode === "api_key" ? (
            <div className="space-y-1">
              <label className="text-xs font-medium">
                {t("localApiKeyLabel")} <span className="text-destructive">*</span>
              </label>
              <div className="flex gap-1.5">
                <input
                  type={showSecrets.local_api_key ? "text" : "password"}
                  defaultValue={board.local_api_key === "***" ? "" : (board.local_api_key ?? "")}
                  onBlur={(e) => {
                    const val = e.target.value;
                    if (val && val !== "***" && val !== board.local_api_key) {
                      onUpdate(board.id, { local_api_key: val });
                    }
                  }}
                  placeholder={hasLocalKey ? t("localApiKeySetPlaceholder") : t("localApiKeyPlaceholder")}
                  className="flex-1 h-8 px-2 text-xs rounded-md border bg-background font-mono"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowSecrets((prev) => ({ ...prev, local_api_key: !prev.local_api_key }))}
                  aria-label={showSecrets.local_api_key ? t("hideSecretAriaLabel") : t("showSecretAriaLabel")}
                  className="h-8 w-8 p-0"
                  disabled={board.local_api_key === "***"}
                >
                  {showSecrets.local_api_key ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </Button>
              </div>
              <p className="text-[10px] text-muted-foreground">
                {t.rich("localApiKeyHelp", {
                  link: (chunks) => (
                    <a
                      href="https://fiestaboard.app/docs/setup/api-keys"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline"
                    >
                      {chunks}
                    </a>
                  ),
                })}
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              <label className="text-xs font-medium">{t("enablementTokenLabel")}</label>
              <div className="flex gap-1.5">
                <input
                  type={showSecrets.enablement_token ? "text" : "password"}
                  value={enablementToken}
                  onChange={(e) => setEnablementToken(e.target.value)}
                  placeholder={t("enablementTokenPlaceholder")}
                  className="flex-1 h-8 px-2 text-xs rounded-md border bg-background font-mono"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowSecrets((prev) => ({ ...prev, enablement_token: !prev.enablement_token }))}
                  aria-label={showSecrets.enablement_token ? t("hideSecretAriaLabel") : t("showSecretAriaLabel")}
                  className="h-8 w-8 p-0"
                >
                  {showSecrets.enablement_token ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </Button>
              </div>
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
            </div>
          )}
        </>
      )}

      {/* Cloud API Fields (single boards — arrays use the token below) */}
      {apiMode === "cloud" && !isArray && (
        <div className="space-y-1">
          <label className="text-xs font-medium">
            {t("cloudKeyLabel")} <span className="text-destructive">*</span>
          </label>
          <div className="flex gap-1.5">
            <input
              type={showSecrets.cloud_key ? "text" : "password"}
              defaultValue={board.cloud_key === "***" ? "" : (board.cloud_key ?? "")}
              onBlur={(e) => {
                const val = e.target.value;
                if (val && val !== "***" && val !== board.cloud_key) {
                  onUpdate(board.id, { cloud_key: val });
                }
              }}
              placeholder={hasCloudKey ? t("cloudKeySetPlaceholder") : t("cloudKeyPlaceholder")}
              className="flex-1 h-8 px-2 text-xs rounded-md border bg-background font-mono"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowSecrets((prev) => ({ ...prev, cloud_key: !prev.cloud_key }))}
              aria-label={showSecrets.cloud_key ? t("hideSecretAriaLabel") : t("showSecretAriaLabel")}
              className="h-8 w-8 p-0"
              disabled={board.cloud_key === "***"}
            >
              {showSecrets.cloud_key ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            </Button>
          </div>
          <p className="text-[10px] text-muted-foreground">{t("cloudKeyHelp")}</p>
        </div>
      )}

      {/* Note-array Cloud API token (X-Vestaboard-Token) */}
      {isArray && apiMode === "cloud" && (
        <div className="space-y-1">
          <label className="text-xs font-medium" htmlFor={`note-array-token-${board.id}`}>
            {t("noteArrayTokenLabel")}
          </label>
          <div className="flex gap-1.5">
            <input
              id={`note-array-token-${board.id}`}
              type={showSecrets.note_array_token ? "text" : "password"}
              defaultValue={board.note_array_token === "***" ? "" : (board.note_array_token ?? "")}
              onBlur={(e) => {
                const val = e.target.value;
                if (val && val !== "***" && val !== board.note_array_token) {
                  onUpdate(board.id, { note_array_token: val });
                }
              }}
              placeholder={hasNoteArrayToken ? t("noteArrayTokenSetPlaceholder") : t("noteArrayTokenPlaceholder")}
              className="flex-1 h-8 px-2 text-xs rounded-md border bg-background font-mono"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowSecrets((prev) => ({ ...prev, note_array_token: !prev.note_array_token }))}
              aria-label={showSecrets.note_array_token ? t("hideSecretAriaLabel") : t("showSecretAriaLabel")}
              className="h-8 w-8 p-0"
              disabled={board.note_array_token === "***"}
            >
              {showSecrets.note_array_token ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            </Button>
          </div>
          <p className="text-[10px] text-muted-foreground">{t("noteArrayTokenHelp")}</p>
        </div>
      )}

      {/* Validation message */}
      {!isConfigured && (
        <div className="flex items-center gap-1.5 p-1.5 rounded-md bg-destructive/10 text-foreground text-[10px]">
          <AlertCircle className="h-3 w-3 flex-shrink-0" />
          <span>
            {isArray
              ? apiMode === "local"
                ? t("tileGrid.assignRequired")
                : t("noteArrayTokenRequired")
              : apiMode === "local"
                ? t("localApiRequired")
                : t("cloudApiRequired")}
          </span>
        </div>
      )}
    </div>
  );
}

export function DisplaySettings() {
  const t = useTranslations("displaySettings");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const { data: boardSettings, isLoading } = useBoardSettings();
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
      toast.success(t("boardRemoved"));
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const boards = boardSettings?.boards ?? [];

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
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-4 w-48" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Monitor className="h-4 w-4" />
          {t("title")}
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-3">
          {boards.map((board) => {
            const isPaused = board.paused === true;
            const apiMode = board.api_mode ?? "local";
            const hasLocalKey = board.local_api_key === "***" || Boolean(board.local_api_key);
            const hasCloudKey = board.cloud_key === "***" || Boolean(board.cloud_key);
            const hasHost = Boolean(board.host);
            // Same rule as BoardConnectionForm: cloud arrays connect via their
            // token, local arrays via assigned tiles, flagship/note via the
            // selected API mode's credentials.
            const isConnected = isNoteArray(board.device_type)
              ? (board.api_mode ?? "cloud") === "local"
                ? countAssignedTiles(board) > 0
                : board.note_array_token === "***" || Boolean(board.note_array_token)
              : (apiMode === "local" && hasLocalKey && hasHost) || (apiMode === "cloud" && hasCloudKey);

            return (
              <Collapsible
                key={board.id}
                data-testid="board-card"
                data-paused={isPaused ? "true" : undefined}
                className={`rounded-lg border overflow-hidden ${isPaused ? "border-amber-500/60 bg-amber-500/5" : ""}`}
              >
                <CollapsibleTrigger className="flex items-center gap-3 p-3 w-full text-left hover:bg-muted/40 transition-colors [&[data-state=open]>div:first-child>svg:first-child]:hidden [&[data-state=closed]>div:first-child>svg:last-child]:hidden">
                  <div className="flex-shrink-0 text-muted-foreground">
                    <ChevronRight className="h-4 w-4" />
                    <ChevronDown className="h-4 w-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{board.name || t("unnamedBoard")}</div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="capitalize">{board.device_type}</span>
                      <span>•</span>
                      <BoardSizeIndicator
                        deviceType={board.device_type}
                        notesWide={board.notes_wide}
                        notesTall={board.notes_tall}
                      />
                      <span>•</span>
                      <div
                        className="h-3 w-3 rounded border"
                        style={{
                          backgroundColor:
                            board.board_color === "white"
                              ? "var(--color-board-surface-light)"
                              : "var(--color-board-surface-dark)",
                        }}
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
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
                    {isConnected ? (
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
                  </div>
                </CollapsibleTrigger>

                <CollapsibleContent>
                  <div className="border-t px-4 pb-4 pt-3 space-y-3">
                    {/* Pause / Resume row (issue #970) */}
                    <div
                      className={`flex items-center justify-between rounded-md border px-3 py-2 ${
                        isPaused ? "border-amber-500/60 bg-amber-500/10" : "border-transparent bg-muted/30"
                      }`}
                    >
                      <div className="flex items-start gap-2 min-w-0">
                        <Pause
                          className={`h-3.5 w-3.5 mt-0.5 flex-shrink-0 ${
                            isPaused ? "text-amber-600" : "text-muted-foreground"
                          }`}
                        />
                        <div className="min-w-0">
                          <div className="text-xs font-medium">
                            {isPaused ? t("pause.resumeToggle") : t("pause.toggle")}
                          </div>
                          <div className="text-[11px] text-muted-foreground">{t("pause.tooltip")}</div>
                        </div>
                      </div>
                      <Switch
                        checked={isPaused}
                        onCheckedChange={(checked) => handleTogglePaused(board.id, checked)}
                        aria-label={isPaused ? t("pause.resumeToggle") : t("pause.toggle")}
                        data-testid="board-pause-switch"
                      />
                    </div>

                    {/* Type + Color row */}
                    <div className="space-y-2">
                      <div className="flex items-center gap-4 flex-wrap">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] text-muted-foreground">{t("typeLabel")}</span>
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
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] text-muted-foreground">{t("colorLabel")}</span>
                          <div className="flex gap-2">
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
                          </div>
                        </div>
                      </div>

                      {/* Custom W×H inputs (note arrays only) */}
                      {(customOpen[board.id] || currentConfigValue(board) === "custom") && (
                        <div className="space-y-1">
                          <div className="flex items-end gap-2">
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
                            <span className="pb-1.5 text-xs text-muted-foreground">×</span>
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
                          </div>
                          {dimError[board.id] && (
                            <p role="alert" className="text-[10px] text-destructive">
                              {dimError[board.id]}
                            </p>
                          )}
                        </div>
                      )}

                      {/* Auto-detect from board */}
                      <div className="space-y-1">
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
                          <div role="alert" className="flex items-center gap-1.5 text-destructive text-[10px]">
                            <AlertCircle className="h-3 w-3 flex-shrink-0" />
                            <span>{detectError[board.id]}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Connection section */}
                    <div className="border-t pt-3">
                      <BoardConnectionForm board={board} onUpdate={handleUpdateBoard} />
                    </div>

                    {/* Remove board - bottom */}
                    <div className="border-t pt-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-[11px] text-muted-foreground hover:text-destructive h-7 px-2"
                        onClick={() => handleRemoveBoard(board.id)}
                        disabled={boards.length <= 1}
                      >
                        <Trash2 className="h-3 w-3 mr-1" />
                        {t("removeBoard")}
                      </Button>
                    </div>
                  </div>
                </CollapsibleContent>
              </Collapsible>
            );
          })}
        </div>

        {/* Add Board */}
        <div className="pt-2">
          {!showTypePicker ? (
            <Button variant="outline" size="sm" className="text-xs" onClick={() => setShowTypePicker(true)}>
              <Plus className="h-3 w-3 mr-1" />
              {t("addBoard")}
            </Button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">{t("selectType")}</span>
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
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
