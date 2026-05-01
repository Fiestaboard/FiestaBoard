"use client";

import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { MapPin, Loader2 } from "lucide-react";
import { api, LocationSettings } from "@/lib/api";
import { queryKeys } from "@/hooks/use-board";

export function LocationSettingsCard() {
  const t = useTranslations("locationSettings");
  const tCommon = useTranslations("common");
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
      toast.success(t("toastSaved"));
      setIsDirty(false);
    },
    onError: (err: Error) => {
      toast.error(t("toastSaveFailed", { error: err.message }));
    },
  });

  const handleSave = () => {
    const latStr = latitude.trim();
    const lonStr = longitude.trim();
    const lat = latStr ? parseFloat(latStr) : null;
    const lon = lonStr ? parseFloat(lonStr) : null;

    if (latStr && (lat === null || isNaN(lat) || lat < -90 || lat > 90)) {
      toast.error(t("latitudeRange"));
      return;
    }
    if (lonStr && (lon === null || isNaN(lon) || lon < -180 || lon > 180)) {
      toast.error(t("longitudeRange"));
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
          {t("title")}
        </CardTitle>
        <CardDescription>
          {t("description")}
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
                <Label htmlFor="latitude">{t("latitudeLabel")}</Label>
                <Input
                  id="latitude"
                  type="number"
                  step="any"
                  min={-90}
                  max={90}
                  placeholder={t("latitudePlaceholder")}
                  value={latitude}
                  onChange={(e) => handleLatChange(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="longitude">{t("longitudeLabel")}</Label>
                <Input
                  id="longitude"
                  type="number"
                  step="any"
                  min={-180}
                  max={180}
                  placeholder={t("longitudePlaceholder")}
                  value={longitude}
                  onChange={(e) => handleLonChange(e.target.value)}
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              {t("tip")}
            </p>
            <div className="flex gap-2">
              <Button
                onClick={handleSave}
                disabled={mutation.isPending || !isDirty}
                size="sm"
              >
                {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {tCommon("save")}
              </Button>
              {isConfigured && (
                <Button
                  variant="outline"
                  onClick={handleClear}
                  disabled={mutation.isPending}
                  size="sm"
                >
                  {t("clear")}
                </Button>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
