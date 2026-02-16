"use client";

import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Monitor, Smartphone, Plus, Trash2 } from "lucide-react";
import { api, DeviceType, BoardInstance } from "@/lib/api";
import { useBoardSettings } from "@/hooks/use-board";

export function DisplaySettings() {
  const queryClient = useQueryClient();
  const { data: boardSettings, isLoading } = useBoardSettings();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["board-settings"] });
    queryClient.invalidateQueries({ queryKey: ["all-settings"] });
  };

  const updateMutation = useMutation({
    mutationFn: (updates: { board_type?: "black" | "white" | null; boards?: BoardInstance[] }) =>
      api.updateBoardSettings(updates),
    onSuccess: () => {
      invalidate();
      toast.success("Display settings saved");
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const addMutation = useMutation({
    mutationFn: (board: { device_type: DeviceType; name?: string; board_color?: "black" | "white" }) =>
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
          Board Display
        </CardTitle>
        <CardDescription>
          Configure your Vestaboard devices and display style
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Board Instances */}
        <div className="space-y-3">
          <Label className="text-sm font-medium">Your Boards</Label>
          <p className="text-xs text-muted-foreground">
            Add each Vestaboard you own. Pages and schedules adapt to your configured boards.
          </p>
          <div className="space-y-3">
            {boards.map((board) => (
              <div key={board.id} className="flex items-center gap-3 p-3 rounded-lg border bg-muted/30">
                {board.device_type === "note" ? (
                  <Smartphone className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                ) : (
                  <Monitor className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0 space-y-1.5">
                  <Input
                    value={board.name}
                    onChange={(e) => handleUpdateBoard(board.id, { name: e.target.value })}
                    className="h-7 text-sm font-medium bg-transparent border-0 border-b border-transparent hover:border-border focus:border-border rounded-none px-0"
                  />
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span>{board.device_type === "flagship" ? "22×6" : "15×3"}</span>
                    <span>•</span>
                    <button
                      onClick={() => handleUpdateBoard(board.id, {
                        board_color: board.board_color === "white" ? "black" : "white"
                      })}
                      className="flex items-center gap-1 hover:text-foreground transition-colors"
                    >
                      <div
                        className="h-3 w-3 rounded border"
                        style={{ backgroundColor: board.board_color === "white" ? "#fafafa" : "#0d0d0d" }}
                      />
                      {board.board_color === "white" ? "White" : "Black"}
                    </button>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive flex-shrink-0"
                  onClick={() => handleRemoveBoard(board.id)}
                  disabled={boards.length <= 1}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        </div>

        {/* Add Board */}
        <div className="flex items-center gap-2 pt-2">
          <Button
            variant="outline"
            size="sm"
            className="text-xs"
            onClick={() => handleAddBoard("flagship")}
          >
            <Plus className="h-3 w-3 mr-1" />
            <Monitor className="h-3 w-3 mr-1" />
            Flagship
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-xs"
            onClick={() => handleAddBoard("note")}
          >
            <Plus className="h-3 w-3 mr-1" />
            <Smartphone className="h-3 w-3 mr-1" />
            Note
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
