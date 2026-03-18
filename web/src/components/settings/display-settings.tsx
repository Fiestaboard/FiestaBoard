"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";
import { toast } from "sonner";
import {
  Monitor, Smartphone, Plus, Trash2, ChevronDown, ChevronRight,
  Eye, EyeOff, AlertCircle, Check, Key, KeyRound, Loader2,
} from "lucide-react";
import { Badge as BadgeUI } from "@/components/ui/badge";
import { api, DeviceType, BoardInstance } from "@/lib/api";
import { useBoardSettings, queryKeys } from "@/hooks/use-board";


function BoardConnectionForm({
  board,
  onUpdate,
}: {
  board: BoardInstance;
  onUpdate: (boardId: string, updates: Partial<BoardInstance>) => void;
}) {
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [localKeyMode, setLocalKeyMode] = useState<"api_key" | "enablement_token">("api_key");
  const [enablementToken, setEnablementToken] = useState("");
  const [isEnabling, setIsEnabling] = useState(false);

  const apiMode = board.api_mode ?? "local";
  const hasLocalKey = board.local_api_key === "***" || (board.local_api_key && board.local_api_key.length > 0);
  const hasCloudKey = board.cloud_key === "***" || (board.cloud_key && board.cloud_key.length > 0);
  const hasHost = board.host && board.host.length > 0;

  const isConfigured =
    (apiMode === "local" && hasLocalKey && hasHost) ||
    (apiMode === "cloud" && hasCloudKey);

  const handleEnableLocalApi = async () => {
    if (!board.host || !enablementToken) {
      toast.error("Board host and enablement token are required");
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
        toast.success("Local API enabled! API key retrieved and saved.");
      } else {
        toast.error(result.message || "Failed to enable local API");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to enable local API");
    } finally {
      setIsEnabling(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label className="text-xs font-medium">Connection</Label>
        {isConfigured ? (
          <BadgeUI variant="default" className="text-[10px] h-5 bg-board-green">
            <Check className="h-2.5 w-2.5 mr-0.5" />
            Connected
          </BadgeUI>
        ) : (
          <BadgeUI variant="destructive" className="text-[10px] h-5">
            <AlertCircle className="h-2.5 w-2.5 mr-0.5" />
            Not configured
          </BadgeUI>
        )}
      </div>

      {/* API Mode */}
      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={() => onUpdate(board.id, { api_mode: "local" })}
          className={`p-2 rounded-md border text-left transition-colors ${
            apiMode === "local"
              ? "border-primary bg-primary/10"
              : "border-muted hover:border-primary/50"
          }`}
        >
          <div className="text-xs font-medium">Local API</div>
          <div className="text-[10px] text-muted-foreground">Direct connection</div>
        </button>
        <button
          onClick={() => onUpdate(board.id, { api_mode: "cloud" })}
          className={`p-2 rounded-md border text-left transition-colors ${
            apiMode === "cloud"
              ? "border-primary bg-primary/10"
              : "border-muted hover:border-primary/50"
          }`}
        >
          <div className="text-xs font-medium">Cloud API</div>
          <div className="text-[10px] text-muted-foreground">Via cloud servers</div>
        </button>
      </div>

      {/* Local API Fields */}
      {apiMode === "local" && (
        <>
          <div className="space-y-1">
            <label className="text-xs font-medium">
              Board Host <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              defaultValue={board.host ?? ""}
              onBlur={(e) => {
                if (e.target.value !== board.host) {
                  onUpdate(board.id, { host: e.target.value });
                }
              }}
              placeholder="192.168.1.100"
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
              API Key
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
              Enablement Token
            </button>
          </div>

          {localKeyMode === "api_key" ? (
            <div className="space-y-1">
              <label className="text-xs font-medium">
                Local API Key <span className="text-destructive">*</span>
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
                  placeholder={hasLocalKey ? "••••••••••• (set)" : "Enter local API key"}
                  className="flex-1 h-8 px-2 text-xs rounded-md border bg-background font-mono"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowSecrets((prev) => ({ ...prev, local_api_key: !prev.local_api_key }))}
                  className="h-8 w-8 p-0"
                  disabled={board.local_api_key === "***"}
                >
                  {showSecrets.local_api_key ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </Button>
              </div>
              <p className="text-[10px] text-muted-foreground">
                Get your key by requesting an enablement token at{" "}
                <a href="https://www.vestaboard.com/local-api" target="_blank" rel="noopener noreferrer" className="underline">vestaboard.com/local-api</a>
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              <label className="text-xs font-medium">Enablement Token</label>
              <div className="flex gap-1.5">
                <input
                  type={showSecrets.enablement_token ? "text" : "password"}
                  value={enablementToken}
                  onChange={(e) => setEnablementToken(e.target.value)}
                  placeholder="Token from vestaboard.com/local-api"
                  className="flex-1 h-8 px-2 text-xs rounded-md border bg-background font-mono"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowSecrets((prev) => ({ ...prev, enablement_token: !prev.enablement_token }))}
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
                    Enabling...
                  </>
                ) : (
                  "Get API Key from Board"
                )}
              </Button>
            </div>
          )}
        </>
      )}

      {/* Cloud API Fields */}
      {apiMode === "cloud" && (
        <div className="space-y-1">
          <label className="text-xs font-medium">
            Read/Write API Key <span className="text-destructive">*</span>
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
              placeholder={hasCloudKey ? "••••••••••• (set)" : "Enter R/W API key"}
              className="flex-1 h-8 px-2 text-xs rounded-md border bg-background font-mono"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowSecrets((prev) => ({ ...prev, cloud_key: !prev.cloud_key }))}
              className="h-8 w-8 p-0"
              disabled={board.cloud_key === "***"}
            >
              {showSecrets.cloud_key ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            </Button>
          </div>
          <p className="text-[10px] text-muted-foreground">
            Found in your board app under Settings → Integrations → Read/Write API
          </p>
        </div>
      )}

      {/* Validation message */}
      {!isConfigured && (
        <div className="flex items-center gap-1.5 p-1.5 rounded-md bg-destructive/10 text-foreground text-[10px]">
          <AlertCircle className="h-3 w-3 flex-shrink-0" />
          <span>
            {apiMode === "local"
              ? "Local API key and host are required"
              : "Cloud API key is required"}
          </span>
        </div>
      )}
    </div>
  );
}


export function DisplaySettings() {
  const queryClient = useQueryClient();
  const { data: boardSettings, isLoading } = useBoardSettings();
  const [showTypePicker, setShowTypePicker] = useState(false);
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
    queryClient.invalidateQueries({ queryKey: ["all-settings"] });
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
    mutationFn: (board: Partial<BoardInstance> & { device_type: DeviceType }) =>
      api.addBoard(board),
    onSuccess: () => {
      invalidate();
      toast.success("Board added");
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (boardId: string) => api.removeBoard(boardId),
    onSuccess: () => {
      invalidate();
      toast.success("Board removed");
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const boards = boardSettings?.boards ?? [];

  const handleAddBoard = (deviceType: DeviceType) => {
    addMutation.mutate({ device_type: deviceType });
    setShowTypePicker(false);
  };

  const handleRemoveBoard = (boardId: string) => {
    if (boards.length <= 1) {
      toast.error("At least one board is required");
      return;
    }
    removeMutation.mutate(boardId);
  };

  const handleUpdateBoard = (boardId: string, updates: Partial<BoardInstance>) => {
    const updated = boards.map((b) =>
      b.id === boardId ? { ...b, ...updates } : b
    );
    updateMutation.mutate({ boards: updated });
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
          Your Boards
        </CardTitle>
        <CardDescription>
          Add each Vestaboard you own and configure its connection.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-3">
          {boards.map((board) => {
            const isEnabled = board.enabled !== false;
            const apiMode = board.api_mode ?? "local";
            const hasLocalKey = board.local_api_key === "***" || Boolean(board.local_api_key);
            const hasCloudKey = board.cloud_key === "***" || Boolean(board.cloud_key);
            const hasHost = Boolean(board.host);
            const isConnected =
              (apiMode === "local" && hasLocalKey && hasHost) ||
              (apiMode === "cloud" && hasCloudKey);

            return (
              <Collapsible
                key={board.id}
                className={`rounded-lg border overflow-hidden ${
                  isEnabled ? "" : "bg-muted/30"
                }`}
              >
                <CollapsibleTrigger className="flex items-center gap-3 p-3 w-full text-left hover:bg-muted/40 transition-colors [&[data-state=open]>div:first-child>svg:first-child]:hidden [&[data-state=closed]>div:first-child>svg:last-child]:hidden">
                  <div className="flex-shrink-0 text-muted-foreground">
                    <ChevronRight className="h-4 w-4" />
                    <ChevronDown className="h-4 w-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{board.name || "Unnamed Board"}</div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="capitalize">{board.device_type}</span>
                      <span>•</span>
                      <span>{board.device_type === "flagship" ? "22×6" : "15×3"}</span>
                      <span>•</span>
                      <div
                        className="h-3 w-3 rounded border"
                        style={{ backgroundColor: board.board_color === "white" ? "var(--color-board-surface-light)" : "var(--color-board-surface-dark)" }}
                      />
                      {!isEnabled && (
                        <>
                          <span>•</span>
                          <span className="italic">Disabled</span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex-shrink-0">
                    {isConnected ? (
                      <BadgeUI variant="default" className="text-[10px] h-5 bg-board-green">
                        <Check className="h-2.5 w-2.5 mr-0.5" />
                        Connected
                      </BadgeUI>
                    ) : (
                      <BadgeUI variant="destructive" className="text-[10px] h-5">
                        <AlertCircle className="h-2.5 w-2.5 mr-0.5" />
                        Not configured
                      </BadgeUI>
                    )}
                  </div>
                </CollapsibleTrigger>

                <CollapsibleContent>
                  <div className="border-t px-4 pb-4 pt-3 space-y-3">
                    {/* Name + Enabled row */}
                    <div className="flex items-center gap-3">
                      <div className="flex-1">
                        <Input
                          defaultValue={board.name}
                          onBlur={(e) => {
                            if (e.target.value !== board.name) {
                              handleUpdateBoard(board.id, { name: e.target.value });
                            }
                          }}
                          placeholder="e.g. Kitchen Board, Office Note"
                          className="h-8 text-xs"
                        />
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <label className="text-[11px] text-muted-foreground">Enabled</label>
                        <Switch
                          checked={isEnabled}
                          onCheckedChange={(checked) =>
                            handleUpdateBoard(board.id, { enabled: checked })
                          }
                        />
                      </div>
                    </div>

                    {/* Type + Color row */}
                    <div className="flex items-center gap-4">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] text-muted-foreground">Type</span>
                        <div className="flex gap-1">
                          <button
                            onClick={() => handleUpdateBoard(board.id, { device_type: "flagship" })}
                            className={`px-2.5 py-1 rounded-full border text-[11px] transition-colors ${
                              board.device_type === "flagship"
                                ? "border-primary bg-primary/10 text-foreground"
                                : "border-transparent text-muted-foreground hover:text-foreground"
                            }`}
                          >
                            Flagship
                          </button>
                          <button
                            onClick={() => handleUpdateBoard(board.id, { device_type: "note" })}
                            className={`px-2.5 py-1 rounded-full border text-[11px] transition-colors ${
                              board.device_type === "note"
                                ? "border-primary bg-primary/10 text-foreground"
                                : "border-transparent text-muted-foreground hover:text-foreground"
                            }`}
                          >
                            Note
                          </button>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] text-muted-foreground">Color</span>
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleUpdateBoard(board.id, { board_color: "black" })}
                            aria-label="Black"
                            className={`h-6 w-6 rounded-full border-2 bg-board-surface-dark transition-colors ${
                              board.board_color === "black"
                                ? "border-primary ring-2 ring-primary/30"
                                : "border-border hover:border-muted-foreground"
                            }`}
                          />
                          <button
                            onClick={() => handleUpdateBoard(board.id, { board_color: "white" })}
                            aria-label="White"
                            className={`h-6 w-6 rounded-full border-2 bg-board-surface-light transition-colors ${
                              board.board_color === "white"
                                ? "border-primary ring-2 ring-primary/30"
                                : "border-border hover:border-muted-foreground"
                            }`}
                          />
                        </div>
                      </div>
                    </div>

                    {/* Connection section */}
                    <div className="border-t pt-3">
                      <BoardConnectionForm
                        board={board}
                        onUpdate={handleUpdateBoard}
                      />
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
                        Remove Board
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
            <Button
              variant="outline"
              size="sm"
              className="text-xs"
              onClick={() => setShowTypePicker(true)}
            >
              <Plus className="h-3 w-3 mr-1" />
              Add Board
            </Button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Select type:</span>
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => handleAddBoard("flagship")}
              >
                <Monitor className="h-3 w-3 mr-1" />
                Flagship
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => handleAddBoard("note")}
              >
                <Smartphone className="h-3 w-3 mr-1" />
                Note
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground"
                onClick={() => setShowTypePicker(false)}
              >
                Cancel
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
