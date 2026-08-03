"use client";

import {
  Box,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Flex,
  Grid,
  Input,
  Label,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, LocateFixed, MapPin } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { queryKeys } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type { LocationSettings } from "@/lib/api";
import { api } from "@/lib/api";

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
  const [isGeolocating, setIsGeolocating] = useState(false);

  useEffect(() => {
    if (location) {
      setLatitude(location.latitude != null ? String(location.latitude) : "");
      setLongitude(location.longitude != null ? String(location.longitude) : "");
      setIsDirty(false);
    }
  }, [location]);

  const mutation = useMutation({
    mutationFn: (settings: Partial<LocationSettings>) => api.updateLocationSettings(settings),
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

  const handleUseMyLocation = () => {
    if (!navigator.geolocation) {
      toast.error(t("locationUnavailable"));
      return;
    }
    setIsGeolocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = position.coords.latitude.toFixed(6);
        const lon = position.coords.longitude.toFixed(6);
        setLatitude(lat);
        setLongitude(lon);
        setIsDirty(true);
        setIsGeolocating(false);
      },
      (error) => {
        setIsGeolocating(false);
        if (error.code === error.PERMISSION_DENIED) {
          toast.error(t("locationDenied"));
        } else {
          toast.error(t("locationUnavailable"));
        }
      },
      { timeout: 10000 },
    );
  };

  const isConfigured = location?.latitude != null && location?.longitude != null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <MapPin className="h-4 w-4" />
          {t("title")}
        </CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <Stack gap="3">
            <Box className="h-10 bg-muted animate-pulse rounded" />
            <Box className="h-10 bg-muted animate-pulse rounded" />
          </Stack>
        ) : (
          <>
            <Grid cols="2" gap="4">
              <Stack gap="2">
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
              </Stack>
              <Stack gap="2">
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
              </Stack>
            </Grid>
            <Text size="xs" tone="muted">
              {t("tip")}
            </Text>
            <Flex gap="2">
              <Button
                variant="outline"
                onClick={handleUseMyLocation}
                disabled={mutation.isPending || isGeolocating}
                size="sm"
              >
                {isGeolocating ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <LocateFixed className="mr-2 h-4 w-4" />
                )}
                {isGeolocating ? t("locating") : t("useMyLocation")}
              </Button>
              <Button onClick={handleSave} disabled={mutation.isPending || !isDirty} size="sm">
                {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {tCommon("save")}
              </Button>
              {isConfigured && (
                <Button variant="outline" onClick={handleClear} disabled={mutation.isPending} size="sm">
                  {t("clear")}
                </Button>
              )}
            </Flex>
          </>
        )}
      </CardContent>
    </Card>
  );
}
