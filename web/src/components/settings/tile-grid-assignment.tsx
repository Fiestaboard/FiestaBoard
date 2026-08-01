"use client";

import {
  Badge as BadgeUI,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@fiestaboard/ui";
import { AlertCircle, Check, Key, KeyRound, Loader2, Plus, Radar, ScanSearch, Trash2, Wifi } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import type { BoardInstance, DiscoveredBoard, NoteArrayTile } from "@/lib/api";
import { api } from "@/lib/api";

const MASKED = "***";
const DEFAULT_PORT = 7000;

function tileKey(row: number, col: number) {
  return `${row}:${col}`;
}

/** Reading-order slot number (matches the backend identify pattern). */
function slotNumber(row: number, col: number, notesWide: number) {
  return row * notesWide + col + 1;
}

interface SlotFormState {
  host: string;
  port: number;
  localApiKey: string;
  keyMode: "api_key" | "enablement_token";
  enablementToken: string;
}

/**
 * Click-to-assign grid for local-mode note arrays: one slot per Note in the
 * W×H array. Clicking a slot opens a dialog to assign that physical board's
 * IP + Local API key (manually, via network scan, or via enablement token),
 * test it, and flash an identify pattern so the user can verify which
 * physical board sits in which slot.
 */
export function TileGridAssignment({
  board,
  onUpdate,
}: {
  board: BoardInstance;
  onUpdate: (boardId: string, updates: Partial<BoardInstance>) => void;
}) {
  const t = useTranslations("displaySettings");
  const notesWide = board.notes_wide ?? 1;
  const notesTall = board.notes_tall ?? 1;
  const totalSlots = notesWide * notesTall;
  const tiles = useMemo(() => board.tiles ?? [], [board.tiles]);

  const tilesByPos = useMemo(() => {
    const map = new Map<string, NoteArrayTile>();
    for (const tile of tiles) {
      if (tile.row < notesTall && tile.col < notesWide) {
        map.set(tileKey(tile.row, tile.col), tile);
      }
    }
    return map;
  }, [tiles, notesWide, notesTall]);

  const assignedCount = useMemo(
    // Mirrors the backend's configured_tiles(): a disabled tile is not driven.
    () => [...tilesByPos.values()].filter((tile) => (tile.enabled ?? true) && tile.host && tile.local_api_key).length,
    [tilesByPos],
  );

  const duplicateHosts = useMemo(() => {
    const seen = new Map<string, number>();
    for (const tile of tilesByPos.values()) {
      if (!tile.host) continue;
      const endpoint = `${tile.host}:${tile.port ?? DEFAULT_PORT}`;
      seen.set(endpoint, (seen.get(endpoint) ?? 0) + 1);
    }
    return [...seen.entries()].filter(([, count]) => count > 1).map(([endpoint]) => endpoint);
  }, [tilesByPos]);

  const [editingSlot, setEditingSlot] = useState<{ row: number; col: number } | null>(null);
  const [form, setForm] = useState<SlotFormState>({
    host: "",
    port: DEFAULT_PORT,
    localApiKey: "",
    keyMode: "api_key",
    enablementToken: "",
  });
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<"ok" | "fail" | null>(null);
  const [isIdentifying, setIsIdentifying] = useState(false);
  const [isIdentifyingAll, setIsIdentifyingAll] = useState(false);
  const [isEnabling, setIsEnabling] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [discovered, setDiscovered] = useState<DiscoveredBoard[] | null>(null);

  const openSlot = (row: number, col: number) => {
    const existing = tilesByPos.get(tileKey(row, col));
    setForm({
      host: existing?.host ?? "",
      port: existing?.port ?? DEFAULT_PORT,
      localApiKey: existing?.local_api_key ?? "",
      keyMode: "api_key",
      enablementToken: "",
    });
    setTestResult(null);
    setDiscovered(null);
    setEditingSlot({ row, col });
  };

  const closeDialog = () => {
    setEditingSlot(null);
    setTestResult(null);
    setDiscovered(null);
  };

  /** Arrow-key navigation between slots (buttons stay in the normal tab order). */
  const handleSlotKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, row: number, col: number) => {
    const deltas: Record<string, [number, number]> = {
      ArrowRight: [0, 1],
      ArrowLeft: [0, -1],
      ArrowDown: [1, 0],
      ArrowUp: [-1, 0],
    };
    const delta = deltas[event.key];
    if (!delta) return;
    event.preventDefault();
    const nextRow = Math.min(Math.max(row + delta[0], 0), notesTall - 1);
    const nextCol = Math.min(Math.max(col + delta[1], 0), notesWide - 1);
    event.currentTarget
      .closest('[data-testid="tile-grid"]')
      ?.querySelector<HTMLButtonElement>(`[data-testid="tile-slot-${nextRow}-${nextCol}"]`)
      ?.focus();
  };

  /** Replace this slot's tile in the full tiles list (out-of-range tiles preserved). */
  const writeTiles = (nextForSlot: NoteArrayTile | null) => {
    if (!editingSlot) return;
    const rest = tiles.filter((tile) => !(tile.row === editingSlot.row && tile.col === editingSlot.col));
    onUpdate(board.id, { tiles: nextForSlot ? [...rest, nextForSlot] : rest });
    closeDialog();
  };

  const handleSave = () => {
    if (!editingSlot) return;
    if (!form.host || !form.localApiKey) {
      toast.error(t("tileGrid.hostAndKeyRequired"));
      return;
    }
    writeTiles({
      row: editingSlot.row,
      col: editingSlot.col,
      host: form.host.trim(),
      port: form.port || DEFAULT_PORT,
      local_api_key: form.localApiKey,
      enabled: true,
    });
    toast.success(t("tileGrid.tileSaved"));
  };

  const handleClear = () => {
    writeTiles(null);
    toast.success(t("tileGrid.tileCleared"));
  };

  /** Move the edited tile to another slot; if that slot is occupied, swap. */
  const handleMove = (targetKey: string) => {
    if (!editingSlot || !editingSaved) return;
    const [targetRow, targetCol] = targetKey.split(":").map(Number);
    const next = tiles.map((tile) => {
      if (tile.row === editingSlot.row && tile.col === editingSlot.col) {
        return { ...tile, row: targetRow, col: targetCol };
      }
      if (tile.row === targetRow && tile.col === targetCol) {
        return { ...tile, row: editingSlot.row, col: editingSlot.col };
      }
      return tile;
    });
    onUpdate(board.id, { tiles: next });
    closeDialog();
    toast.success(t("tileGrid.tileMoved", { position: slotNumber(targetRow, targetCol, notesWide) }));
  };

  const handleTest = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const result = await api.testBoardConnection({
        api_mode: "local",
        host: form.host,
        port: form.port || DEFAULT_PORT,
        local_api_key: form.localApiKey,
      });
      setTestResult(result.success ? "ok" : "fail");
      if (!result.success && result.message) toast.error(result.message);
    } catch (error) {
      setTestResult("fail");
      toast.error(error instanceof Error ? error.message : t("tileGrid.testFailed"));
    } finally {
      setIsTesting(false);
    }
  };

  const handleIdentify = async () => {
    if (!editingSlot) return;
    setIsIdentifying(true);
    try {
      const result = await api.identifyBoardTile(
        board.id,
        canIdentifySaved
          ? { target: "tile", row: editingSlot.row, col: editingSlot.col }
          : {
              target: "tile",
              row: editingSlot.row,
              col: editingSlot.col,
              host: form.host,
              port: form.port || DEFAULT_PORT,
              local_api_key: form.localApiKey,
            },
      );
      const ok = result.results.every((r) => r.success);
      if (ok) {
        toast.success(
          t("tileGrid.identifySent", { position: slotNumber(editingSlot.row, editingSlot.col, notesWide) }),
        );
      } else {
        toast.error(t("tileGrid.identifyFailed"));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("tileGrid.identifyFailed"));
    } finally {
      setIsIdentifying(false);
    }
  };

  const handleIdentifyAll = async () => {
    setIsIdentifyingAll(true);
    try {
      const result = await api.identifyBoardTile(board.id, { target: "all" });
      const failed = result.results.filter((r) => !r.success);
      if (failed.length === 0) {
        toast.success(t("tileGrid.identifyAllSent", { count: result.results.length }));
      } else {
        toast.error(t("tileGrid.identifyAllPartial", { failed: failed.length, total: result.results.length }));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("tileGrid.identifyFailed"));
    } finally {
      setIsIdentifyingAll(false);
    }
  };

  const handleEnableLocalApi = async () => {
    if (!form.host || !form.enablementToken) {
      toast.error(t("boardHostAndTokenRequired"));
      return;
    }
    setIsEnabling(true);
    try {
      const result = await api.enableLocalApi({ host: form.host, enablement_token: form.enablementToken });
      if (result.success && result.api_key) {
        setForm((prev) => ({ ...prev, localApiKey: result.api_key ?? "", keyMode: "api_key", enablementToken: "" }));
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

  const handleScan = async () => {
    setIsScanning(true);
    try {
      const result = await api.scanForBoards();
      setDiscovered(result.boards);
      if (result.boards.length === 0) toast.info(t("tileGrid.scanEmpty"));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("tileGrid.scanFailed"));
    } finally {
      setIsScanning(false);
    }
  };

  const assignedHosts = useMemo(() => {
    const hosts = new Map<string, number>();
    for (const [key, tile] of tilesByPos.entries()) {
      if (tile.host) {
        const [row, col] = key.split(":").map(Number);
        hosts.set(tile.host, slotNumber(row, col, notesWide));
      }
    }
    return hosts;
  }, [tilesByPos, notesWide]);

  const editingSaved = editingSlot ? tilesByPos.get(tileKey(editingSlot.row, editingSlot.col)) : undefined;
  const keyReady = form.host.length > 0 && form.localApiKey.length > 0;
  const keyIsPlaintext = keyReady && form.localApiKey !== MASKED;
  // Identify can use the server-side saved credentials only while the form
  // still matches the saved tile exactly (host AND port — a masked key with an
  // edited endpoint must not silently flash the old device); otherwise it
  // needs a plaintext key for the unsaved-credential override.
  const canIdentifySaved = Boolean(
    editingSaved &&
    form.localApiKey === MASKED &&
    form.host === editingSaved.host &&
    (form.port || DEFAULT_PORT) === (editingSaved.port ?? DEFAULT_PORT),
  );
  const canIdentify = canIdentifySaved || keyIsPlaintext;

  return (
    <div className="space-y-2" data-testid="tile-grid-assignment">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium">{t("tileGrid.title")}</span>
          {assignedCount === totalSlots ? (
            <BadgeUI variant="default" className="text-[10px] h-5 bg-board-green">
              <Check className="h-2.5 w-2.5 mr-0.5" />
              {t("tileGrid.completeBadge", { total: totalSlots })}
            </BadgeUI>
          ) : (
            <BadgeUI variant="default" className="text-[10px] h-5 bg-amber-500 text-white">
              {t("tileGrid.partialBadge", { assigned: assignedCount, total: totalSlots })}
            </BadgeUI>
          )}
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="h-7 text-[11px]"
          disabled={assignedCount === 0 || isIdentifyingAll}
          onClick={handleIdentifyAll}
        >
          {isIdentifyingAll ? (
            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
          ) : (
            <ScanSearch className="h-3 w-3 mr-1" />
          )}
          {t("tileGrid.identifyAll")}
        </Button>
      </div>

      <p className="text-[10px] text-muted-foreground">{t("tileGrid.help")}</p>

      {duplicateHosts.length > 0 && (
        <div
          role="alert"
          className="flex items-center gap-1.5 p-1.5 rounded-md bg-amber-500/10 text-foreground text-[10px]"
        >
          <AlertCircle className="h-3 w-3 flex-shrink-0 text-amber-600" />
          <span>{t("tileGrid.duplicateHostWarning", { hosts: duplicateHosts.join(", ") })}</span>
        </div>
      )}

      <div
        className="grid gap-1.5"
        style={{ gridTemplateColumns: `repeat(${notesWide}, minmax(0, 1fr))` }}
        data-testid="tile-grid"
      >
        {Array.from({ length: notesTall }, (_, row) =>
          Array.from({ length: notesWide }, (_, col) => {
            const tile = tilesByPos.get(tileKey(row, col));
            const isAssigned = Boolean(tile?.host && tile?.local_api_key);
            const position = slotNumber(row, col, notesWide);
            return (
              <button
                key={tileKey(row, col)}
                type="button"
                data-testid={`tile-slot-${row}-${col}`}
                data-assigned={isAssigned ? "true" : undefined}
                onClick={() => openSlot(row, col)}
                onKeyDown={(e) => handleSlotKeyDown(e, row, col)}
                aria-label={
                  isAssigned
                    ? t("tileGrid.slotAriaLabelAssigned", { position, row: row + 1, col: col + 1, host: tile?.host })
                    : t("tileGrid.slotAriaLabelEmpty", { position, row: row + 1, col: col + 1 })
                }
                className={`relative flex flex-col items-center justify-center gap-0.5 rounded-md border px-1 py-2 min-h-[52px] text-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  isAssigned
                    ? "border-board-green/60 bg-board-green/5 hover:border-board-green"
                    : "border-dashed border-muted hover:border-primary/60"
                }`}
              >
                <span className="text-[10px] font-semibold text-muted-foreground">{position}</span>
                {isAssigned ? (
                  <span className="flex items-center gap-1 text-[10px] font-mono truncate max-w-full text-foreground">
                    <Wifi className="h-2.5 w-2.5 flex-shrink-0 text-board-green" />
                    {tile?.host}
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                    <Plus className="h-2.5 w-2.5" />
                    {t("tileGrid.assign")}
                  </span>
                )}
              </button>
            );
          }),
        )}
      </div>

      <Dialog open={editingSlot !== null} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editingSlot &&
                t("tileGrid.dialogTitle", {
                  position: slotNumber(editingSlot.row, editingSlot.col, notesWide),
                  row: (editingSlot?.row ?? 0) + 1,
                  col: (editingSlot?.col ?? 0) + 1,
                })}
            </DialogTitle>
            <DialogDescription>{t("tileGrid.dialogDescription")}</DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            {/* Network scan */}
            <div className="space-y-1.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full text-xs"
                disabled={isScanning}
                onClick={handleScan}
              >
                {isScanning ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Radar className="h-3 w-3 mr-1" />}
                {isScanning ? t("tileGrid.scanning") : t("tileGrid.scanNetwork")}
              </Button>
              {discovered && discovered.length > 0 && (
                <p role="status" className="text-[10px] text-muted-foreground">
                  {t("tileGrid.scanFound", { count: discovered.length })}
                </p>
              )}
              {discovered && discovered.length > 0 && (
                <div className="max-h-28 overflow-y-auto rounded-md border divide-y">
                  {discovered.map((found) => {
                    const usedBy = assignedHosts.get(found.ip);
                    return (
                      <button
                        key={`${found.ip}:${found.port}`}
                        type="button"
                        onClick={() => setForm((prev) => ({ ...prev, host: found.ip, port: found.port }))}
                        className={`flex w-full items-center justify-between px-2 py-1.5 text-left text-xs hover:bg-muted/50 ${
                          form.host === found.ip ? "bg-primary/10" : ""
                        }`}
                      >
                        <span className="font-mono">{found.ip}</span>
                        <span className="text-[10px] text-muted-foreground">
                          {usedBy !== undefined
                            ? t("tileGrid.alreadyAssigned", { position: usedBy })
                            : found.hostname || found.source}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Host + port */}
            <div className="flex gap-2">
              <div className="flex-1 space-y-1">
                <label className="text-xs font-medium" htmlFor={`tile-host-${board.id}`}>
                  {t("boardHostLabel")} <span className="text-destructive">*</span>
                </label>
                <input
                  id={`tile-host-${board.id}`}
                  type="text"
                  value={form.host}
                  onChange={(e) => setForm((prev) => ({ ...prev, host: e.target.value }))}
                  placeholder={t("boardHostPlaceholder")}
                  className="w-full h-8 px-2 text-xs rounded-md border bg-background font-mono"
                />
              </div>
              <div className="w-20 space-y-1">
                <label className="text-xs font-medium" htmlFor={`tile-port-${board.id}`}>
                  {t("tileGrid.portLabel")}
                </label>
                <input
                  id={`tile-port-${board.id}`}
                  type="number"
                  min={1}
                  max={65535}
                  value={form.port}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, port: Number.parseInt(e.target.value, 10) || DEFAULT_PORT }))
                  }
                  className="w-full h-8 px-2 text-xs rounded-md border bg-background font-mono"
                />
              </div>
            </div>

            {/* Auth method toggle */}
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                aria-pressed={form.keyMode === "api_key"}
                onClick={() => setForm((prev) => ({ ...prev, keyMode: "api_key" }))}
                className={`flex items-center justify-center gap-1 p-1.5 rounded-md border text-[10px] transition-colors ${
                  form.keyMode === "api_key"
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-muted hover:border-primary/50 text-muted-foreground"
                }`}
              >
                <Key className="h-3 w-3" />
                {t("apiKeyLabel")}
              </button>
              <button
                type="button"
                aria-pressed={form.keyMode === "enablement_token"}
                onClick={() => setForm((prev) => ({ ...prev, keyMode: "enablement_token" }))}
                className={`flex items-center justify-center gap-1 p-1.5 rounded-md border text-[10px] transition-colors ${
                  form.keyMode === "enablement_token"
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-muted hover:border-primary/50 text-muted-foreground"
                }`}
              >
                <KeyRound className="h-3 w-3" />
                {t("enablementTokenLabel")}
              </button>
            </div>

            {form.keyMode === "api_key" ? (
              <div className="space-y-1">
                <label className="text-xs font-medium" htmlFor={`tile-key-${board.id}`}>
                  {t("localApiKeyLabel")} <span className="text-destructive">*</span>
                </label>
                <input
                  id={`tile-key-${board.id}`}
                  type="password"
                  value={form.localApiKey === MASKED ? "" : form.localApiKey}
                  onChange={(e) => setForm((prev) => ({ ...prev, localApiKey: e.target.value }))}
                  placeholder={
                    editingSaved && form.localApiKey === MASKED
                      ? t("localApiKeySetPlaceholder")
                      : t("localApiKeyPlaceholder")
                  }
                  className="w-full h-8 px-2 text-xs rounded-md border bg-background font-mono"
                />
              </div>
            ) : (
              <div className="space-y-1.5">
                <label className="text-xs font-medium" htmlFor={`tile-token-${board.id}`}>
                  {t("enablementTokenLabel")}
                </label>
                <input
                  id={`tile-token-${board.id}`}
                  type="password"
                  value={form.enablementToken}
                  onChange={(e) => setForm((prev) => ({ ...prev, enablementToken: e.target.value }))}
                  placeholder={t("enablementTokenPlaceholder")}
                  className="w-full h-8 px-2 text-xs rounded-md border bg-background font-mono"
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleEnableLocalApi}
                  disabled={!form.host || !form.enablementToken || isEnabling}
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

            {/* Test + Identify */}
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="flex-1 text-xs"
                disabled={!keyIsPlaintext || isTesting}
                onClick={handleTest}
              >
                {isTesting ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Wifi className="h-3 w-3 mr-1" />}
                {t("tileGrid.testTile")}
                {testResult === "ok" && <Check className="h-3 w-3 ml-1 text-board-green" />}
                {testResult === "fail" && <AlertCircle className="h-3 w-3 ml-1 text-destructive" />}
                <span role="status" className="sr-only">
                  {testResult === "ok"
                    ? t("tileGrid.testSuccess")
                    : testResult === "fail"
                      ? t("tileGrid.testFailed")
                      : ""}
                </span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="flex-1 text-xs"
                disabled={!canIdentify || isIdentifying}
                onClick={handleIdentify}
              >
                {isIdentifying ? (
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <ScanSearch className="h-3 w-3 mr-1" />
                )}
                {t("tileGrid.identify")}
              </Button>
            </div>

            {/* Move / swap — rearrange without retyping credentials. A plain
                Select, so it is fully keyboard- and screen-reader-accessible. */}
            {editingSaved && totalSlots > 1 && (
              <div className="space-y-1">
                <label className="text-xs font-medium" htmlFor={`tile-move-${board.id}`}>
                  {t("tileGrid.moveTile")}
                </label>
                <Select value="" onValueChange={handleMove}>
                  <SelectTrigger id={`tile-move-${board.id}`} className="h-8 w-full text-xs">
                    <SelectValue placeholder={t("tileGrid.movePlaceholder")} />
                  </SelectTrigger>
                  {/* Above the dialog overlay (z-[130]) — the shared SelectContent
                      default (z-[120]) would render the options underneath it. */}
                  <SelectContent className="z-[140]">
                    {Array.from({ length: notesTall }, (_, r) =>
                      Array.from({ length: notesWide }, (_, c) => {
                        if (editingSlot && r === editingSlot.row && c === editingSlot.col) return null;
                        const occupant = tilesByPos.get(tileKey(r, c));
                        const position = slotNumber(r, c, notesWide);
                        return (
                          <SelectItem key={tileKey(r, c)} value={tileKey(r, c)} className="text-xs">
                            {occupant?.host
                              ? t("tileGrid.moveTargetOccupied", { position, host: occupant.host })
                              : t("tileGrid.moveTargetEmpty", { position })}
                          </SelectItem>
                        );
                      }),
                    )}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <DialogFooter className="flex-row justify-between sm:justify-between gap-2">
            {editingSaved ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground hover:text-destructive"
                onClick={handleClear}
              >
                <Trash2 className="h-3 w-3 mr-1" />
                {t("tileGrid.clearTile")}
              </Button>
            ) : (
              <span />
            )}
            <Button type="button" size="sm" className="text-xs" disabled={!keyReady} onClick={handleSave}>
              {t("tileGrid.saveTile")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
