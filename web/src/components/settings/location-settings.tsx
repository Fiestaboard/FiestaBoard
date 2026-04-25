"use client";

import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { MapPin, Loader2 } from "lucide-react";
import { api, LocationSettings } from "@/lib/api";
import { queryKeys } from "@/hooks/use-board";

export function LocationSettingsCard() {
  const queryClient = useQueryClient();

  const { data: location, isLoading } = useQuery({
    queryKey: ["settings", "location"],
    queryFn: () => api.getLocationSettings(),
  });

  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [isDirty, setIsDirty] = useState(false);

  useEffect(() => {
    if (location) {
      setLatitude(location.latitude != null ? String(location.latitude) : "");
      setLongitude(location.longitude != null ? String(location.longitude) : "");
      setIsDirty(false);
    }
  }, [location]);

  const mutation = useMutation({
    mutationFn: (settings: Partial<LocationSettings>) =>
      api.updateLocationSettings(settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.schedules("") });
      toast.success("Location settings saved");
      setIsDirty(false);
    },
    onError: (err: Error) => {
      toast.error(`Failed to save location: ${err.message}`);
    },
  });

  const handleSave = () => {
    const latStr = latitude.trim();
    const lonStr = longitude.trim();
    const lat = latStr ? parseFloat(latStr) : null;
    const lon = lonStr ? parseFloat(lonStr) : null;

    if (latStr && (lat === null || isNaN(lat) || lat < -90 || lat > 90)) {
      toast.error("Latitude must be a number between -90 and 90");
      return;
    }
    if (lonStr && (lon === null || isNaN(lon) || lon < -180 || lon > 180)) {
      toast.error("Longitude must be a number between -180 and 180");
      return;
    }

    mutation.mutate({ latitude: lat, longitude: lon });
  };

  const handleClear = () => {
    setLatitude("");
    setLongitude("");
    mutation.mutate({ latitude: null, longitude: null });
  };

  const handleLatChange = (v: string) => {
    setLatitude(v);
    setIsDirty(true);
  };
  const handleLonChange = (v: string) => {
    setLongitude(v);
    setIsDirty(true);
  };

  const isConfigured = location?.latitude != null && location?.longitude != null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <MapPin className="h-4 w-4" />
          Location
        </CardTitle>
        <CardDescription>
          Set your location for sunrise/sunset-based schedules. Coordinates are used to
          calculate sun times daily.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="space-y-3">
            <div className="h-10 bg-muted animate-pulse rounded" />
            <div className="h-10 bg-muted animate-pulse rounded" />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="latitude">Latitude</Label>
                <Input
                  id="latitude"
                  type="number"
                  step="any"
                  min={-90}
                  max={90}
                  placeholder="e.g. 40.7128"
                  value={latitude}
                  onChange={(e) => handleLatChange(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="longitude">Longitude</Label>
                <Input
                  id="longitude"
                  type="number"
                  step="any"
                  min={-180}
                  max={180}
                  placeholder="e.g. -74.0060"
                  value={longitude}
                  onChange={(e) => handleLonChange(e.target.value)}
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Tip: Search for your city on a map service and copy the coordinates.
              Only approximate location is needed for accurate sunrise/sunset times.
            </p>
            <div className="flex gap-2">
              <Button
                onClick={handleSave}
                disabled={mutation.isPending || !isDirty}
                size="sm"
              >
                {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save
              </Button>
              {isConfigured && (
                <Button
                  variant="outline"
                  onClick={handleClear}
                  disabled={mutation.isPending}
                  size="sm"
                >
                  Clear
                </Button>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
