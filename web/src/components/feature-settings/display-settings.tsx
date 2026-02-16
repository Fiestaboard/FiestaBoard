"use client";

import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Monitor, Smartphone } from "lucide-react";
import { api, DeviceType } from "@/lib/api";
import { useBoardSettings } from "@/hooks/use-board";

export function DisplaySettings() {
  const queryClient = useQueryClient();
  const { data: boardSettings, isLoading } = useBoardSettings();
  const [boardType, setBoardType] = useState<"black" | "white">("black");
  const [hasFlagship, setHasFlagship] = useState(true);
  const [hasNote, setHasNote] = useState(false);

  // Initialize from settings
  useEffect(() => {
    if (boardSettings) {
      setBoardType(boardSettings.board_type ?? "black");
      const devices = boardSettings.devices ?? ["flagship"];
      setHasFlagship(devices.includes("flagship"));
      setHasNote(devices.includes("note"));
    }
  }, [boardSettings]);

  const updateMutation = useMutation({
    mutationFn: (updates: { board_type?: "black" | "white" | null; devices?: DeviceType[] }) =>
      api.updateBoardSettings(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["board-settings"] });
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
      toast.success("Display settings saved");
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const handleBoardTypeChange = (isWhite: boolean) => {
    const newType = isWhite ? "white" : "black";
    setBoardType(newType);
    updateMutation.mutate({ board_type: newType });
  };

  const handleDeviceToggle = (device: DeviceType, enabled: boolean) => {
    let newFlagship = hasFlagship;
    let newNote = hasNote;

    if (device === "flagship") newFlagship = enabled;
    if (device === "note") newNote = enabled;

    // Must have at least one device
    if (!newFlagship && !newNote) {
      toast.error("At least one device must be enabled");
      return;
    }

    setHasFlagship(newFlagship);
    setHasNote(newNote);

    const devices: DeviceType[] = [];
    if (newFlagship) devices.push("flagship");
    if (newNote) devices.push("note");
    updateMutation.mutate({ devices });
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
      <CardContent className="space-y-6">
        {/* Device Selection */}
        <div className="space-y-3">
          <Label className="text-sm font-medium">Devices</Label>
          <p className="text-xs text-muted-foreground">
            Select the Vestaboard devices you own. The Pages section will adapt to show pages for your configured devices.
          </p>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Monitor className="h-4 w-4 text-muted-foreground" />
                <div>
                  <span className="text-sm font-medium">Flagship</span>
                  <span className="text-xs text-muted-foreground ml-2">22×6</span>
                </div>
              </div>
              <Switch
                checked={hasFlagship}
                onCheckedChange={(checked) => handleDeviceToggle("flagship", checked)}
              />
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Smartphone className="h-4 w-4 text-muted-foreground" />
                <div>
                  <span className="text-sm font-medium">Note</span>
                  <span className="text-xs text-muted-foreground ml-2">15×3</span>
                </div>
              </div>
              <Switch
                checked={hasNote}
                onCheckedChange={(checked) => handleDeviceToggle("note", checked)}
              />
            </div>
          </div>
        </div>

        {/* Board Color */}
        <div className="space-y-3 pt-3 border-t">
          <Label className="text-sm font-medium">Board Color</Label>
          <p className="text-xs text-muted-foreground">
            Match the preview to your physical board color.
          </p>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div
                className="h-4 w-4 rounded border"
                style={{ backgroundColor: boardType === "white" ? "#fafafa" : "#0d0d0d" }}
              />
              <span className="text-sm font-medium">
                {boardType === "white" ? "White" : "Black"}
              </span>
            </div>
            <Switch
              checked={boardType === "white"}
              onCheckedChange={handleBoardTypeChange}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
