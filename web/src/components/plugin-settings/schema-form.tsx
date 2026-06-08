"use client";

import { Check, ChevronDown, ChevronRight, Copy, Eye, EyeOff, Loader2, MapPin, Plus, Trash2, Zap } from "lucide-react";
import { useTranslations } from "@/i18n/translations";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { TimezonePicker } from "@/components/ui/timezone-picker";
import { api, type QueueTimesPark, type QueueTimesRide } from "@/lib/api";
import { cn } from "@/lib/utils";

import { PagePickerField } from "./page-picker-field";

// JSON Schema types (simplified for our use case)
interface SchemaProperty {
  type: "string" | "number" | "integer" | "boolean" | "array" | "object";
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  enumNames?: string[];
  minimum?: number;
  maximum?: number;
  minItems?: number;
  maxItems?: number;
  items?: SchemaProperty;
  properties?: Record<string, SchemaProperty>;
  required?: string[];
  "ui:widget"?: string;
  "ui:placeholder"?: string;
}

interface JSONSchema {
  type: "object";
  properties: Record<string, SchemaProperty>;
  required?: string[];
}

interface SchemaFormProps {
  schema: JSONSchema;
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
  disabled?: boolean;
  className?: string;
}

// Individual field components
interface FieldProps {
  name: string;
  property: SchemaProperty;
  value: unknown;
  onChange: (value: unknown) => void;
  required?: boolean;
  disabled?: boolean;
}

interface EnumSelectFieldProps {
  name: string;
  property: SchemaProperty;
  enumArray: string[];
  allOptions: string[];
  selectValue: string;
  capitalizeDisplay: (str: string) => string;
  onChange: (value: unknown) => void;
  disabled?: boolean;
}

function EnumSelectField({
  name,
  property,
  enumArray,
  allOptions,
  selectValue,
  capitalizeDisplay,
  onChange,
  disabled,
}: EnumSelectFieldProps) {
  const enumNames = property.enumNames;
  const selectItems = React.useMemo(() => {
    return allOptions.map((option, idx) => {
      const itemKey = `${name}-option-${idx}-${option}`;
      // Look up custom label from enumNames if provided. Use the
      // original enum index (not the deduped one) so labels stay
      // aligned with their values.
      let displayLabel = capitalizeDisplay(option);
      if (enumNames && Array.isArray(enumNames)) {
        const originalIdx = enumArray.indexOf(option);
        if (originalIdx >= 0 && enumNames[originalIdx]) {
          displayLabel = enumNames[originalIdx];
        }
      }
      return (
        <SelectItem key={itemKey} value={option}>
          {displayLabel}
        </SelectItem>
      );
    });
  }, [name, allOptions, enumNames, enumArray, capitalizeDisplay]);

  // Stable onChange handler to prevent re-renders
  const handleValueChange = React.useCallback(
    (newValue: string) => {
      onChange(newValue);
    },
    [onChange],
  );

  return (
    <Select value={selectValue} onValueChange={handleValueChange} disabled={disabled} modal={false}>
      <SelectTrigger id={name}>
        <SelectValue placeholder={property["ui:placeholder"] || `Select ${property.title || name}`} />
      </SelectTrigger>
      <SelectContent className="max-h-[300px] z-[120]" disableHeightConstraint={allOptions.length > 1}>
        {selectItems}
      </SelectContent>
    </Select>
  );
}

function StringField({ name, property, value, onChange, required, disabled }: FieldProps) {
  const [showPassword, setShowPassword] = useState(false);
  const [_timezoneValid, setTimezoneValid] = useState(true);
  const isPassword = property["ui:widget"] === "password";
  const isTextarea = property["ui:widget"] === "textarea";
  const isTimezone = property["ui:widget"] === "timezone";
  const isPagePicker = property["ui:widget"] === "page-picker";

  if (property.enum) {
    // Normalize enum to array of strings - handle all possible formats
    let enumArray: string[] = [];

    // Handle array format
    if (Array.isArray(property.enum)) {
      enumArray = property.enum
        .map((opt) => {
          if (opt === null || opt === undefined) return "";
          return String(opt).trim();
        })
        .filter((opt) => opt.length > 0);
    }
    // Handle single string (shouldn't happen but be defensive)
    else if (typeof property.enum === "string") {
      enumArray = [property.enum.trim()].filter((opt) => opt.length > 0);
    }
    // Handle object with array property (defensive)
    else if (typeof property.enum === "object" && property.enum !== null) {
      const enumObj = property.enum as Record<string, unknown>;
      if (Array.isArray(enumObj.values)) {
        enumArray = enumObj.values.map((opt: unknown) => String(opt).trim()).filter((opt) => opt.length > 0);
      }
    }

    if (enumArray.length > 0) {
      // Use default value if value is undefined, or ensure value matches an enum option
      const defaultValue = property.default !== undefined ? String(property.default) : enumArray[0];
      const currentValue = value !== undefined && value !== null ? String(value) : defaultValue;
      // Ensure value matches one of the enum options, fallback to default or first option
      const selectValue =
        currentValue && enumArray.includes(currentValue)
          ? currentValue
          : defaultValue && enumArray.includes(defaultValue)
            ? defaultValue
            : enumArray[0];

      // Ensure we have all enum options - remove duplicates
      const allOptions = [...new Set(enumArray)];

      // Helper to capitalize first letter for display
      const capitalizeDisplay = (str: string): string => {
        if (!str) return str;
        return str.charAt(0).toUpperCase() + str.slice(1);
      };

      // Render all enum options
      return (
        <EnumSelectField
          name={name}
          property={property}
          enumArray={enumArray}
          allOptions={allOptions}
          selectValue={selectValue}
          capitalizeDisplay={capitalizeDisplay}
          onChange={onChange}
          disabled={disabled}
        />
      );
    }
  }

  if (isTextarea) {
    return (
      <textarea
        id={name}
        value={String(value || "")}
        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
        placeholder={property["ui:placeholder"] || property.description}
        disabled={disabled}
        required={required}
        className={cn(
          "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2",
          "text-sm ring-offset-background placeholder:text-muted-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
      />
    );
  }

  if (isTimezone) {
    return (
      <TimezonePicker
        id={name}
        value={String(value || "")}
        onChange={onChange}
        disabled={disabled}
        onValidationChange={setTimezoneValid}
      />
    );
  }

  if (isPagePicker) {
    return <PagePickerField id={name} value={String(value || "")} onChange={onChange} disabled={disabled} />;
  }

  return (
    <div className="relative">
      <Input
        id={name}
        type={isPassword && !showPassword ? "password" : "text"}
        value={String(value || "")}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
        placeholder={property["ui:placeholder"] || property.description}
        disabled={disabled}
        required={required}
        className={isPassword ? "pr-10" : undefined}
      />
      {isPassword && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
          onClick={() => setShowPassword(!showPassword)}
          tabIndex={-1}
        >
          {showPassword ? (
            <EyeOff className="h-4 w-4 text-muted-foreground" />
          ) : (
            <Eye className="h-4 w-4 text-muted-foreground" />
          )}
        </Button>
      )}
    </div>
  );
}

interface NumberFieldProps extends FieldProps {
  onLocationRequest?: (lat: number, lon: number) => void;
  showLocationButton?: boolean;
  isLocationLoading?: boolean;
}

function NumberEnumField({ name, property, value, onChange, disabled }: FieldProps) {
  const rawEnum = property.enum as unknown[];
  const numericEnum = rawEnum.map((opt) => Number(opt)).filter((n) => Number.isFinite(n));
  const enumNames = property.enumNames;
  const defaultNum =
    property.default !== undefined && Number.isFinite(Number(property.default))
      ? Number(property.default)
      : numericEnum[0];
  const currentNum =
    value !== undefined && value !== null && Number.isFinite(Number(value)) ? Number(value) : defaultNum;
  const selectValue = numericEnum.includes(currentNum) ? String(currentNum) : String(defaultNum);
  return (
    <Select value={selectValue} onValueChange={(v) => onChange(Number(v))} disabled={disabled} modal={false}>
      <SelectTrigger id={name}>
        <SelectValue placeholder={property["ui:placeholder"] || `Select ${property.title || name}`} />
      </SelectTrigger>
      <SelectContent className="max-h-[300px] z-[120]">
        {numericEnum.map((option, idx) => (
          <SelectItem key={`${name}-num-${idx}-${option}`} value={String(option)}>
            {enumNames && enumNames[idx] ? enumNames[idx] : String(option)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function NumberField(props: NumberFieldProps) {
  const {
    name,
    property,
    value,
    onChange,
    required,
    disabled,
    onLocationRequest,
    showLocationButton,
    isLocationLoading,
  } = props;
  const t = useTranslations("schemaForm");
  const [isGettingLocation, setIsGettingLocation] = useState(false);

  // Numeric enum → Select. Honors optional enumNames for friendly labels
  // (e.g. {enum: [0, 5], enumNames: ["Until next page", "5 min"]}).
  // Delegated to a sub-component so the hook order is stable when a field
  // switches between enum and free-number variants.
  const hasNumericEnum =
    property.enum && Array.isArray(property.enum) && property.enum.some((opt) => Number.isFinite(Number(opt)));

  // Local text buffer so the user can freely edit the field (delete the
  // existing value, paste a new one, type intermediate states like "-" or
  // "1.") without each keystroke being parsed/validated and snapping the
  // input back to a previous or default value. We only commit a parsed
  // numeric value upstream when the input is in a valid intermediate state
  // (or empty), and we finalize/validate on blur.
  const [text, setText] = useState<string>(value !== undefined && value !== null ? String(value) : "");
  const [isFocused, setIsFocused] = useState(false);

  // Keep the local text in sync with external value changes (e.g. the
  // "use my location" button) when the user is not actively editing.
  useEffect(() => {
    if (!isFocused) {
      setText(value !== undefined && value !== null ? String(value) : "");
    }
  }, [value, isFocused]);

  if (hasNumericEnum) {
    return <NumberEnumField {...props} />;
  }

  // Helper function to get user-friendly error message
  const getErrorMessage = (error: GeolocationPositionError | null | undefined): string => {
    if (!error) {
      return t("geoErrorGeneric");
    }

    const errorCode = error.code;
    let message = t("geoErrorPrefix") + " ";

    if (errorCode === 1) {
      message += t("geoErrorPermissionDenied");
    } else if (errorCode === 2) {
      const isMacOS = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
      if (isMacOS) {
        message += t("geoErrorUnavailableMac");
      } else {
        message += t("geoErrorUnavailableGeneric");
      }
    } else if (errorCode === 3) {
      message += t("geoErrorTimeout");
    } else {
      message += t("geoErrorOther");
    }

    return message;
  };

  const handleLocationClick = async () => {
    // Check if we're on HTTPS or localhost (required for Safari)
    const isSecure =
      window.location.protocol === "https:" ||
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1";
    if (!isSecure) {
      toast.error(t("geoRequiresHttps"));
      return;
    }

    if (!navigator.geolocation) {
      toast.error(t("geoNotSupported"));
      return;
    }

    if (!onLocationRequest) {
      toast.error(t("geoNoCallback"));
      return;
    }

    setIsGettingLocation(true);

    // Use native geolocation API directly for better control
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setIsGettingLocation(false);
        if (onLocationRequest && position.coords) {
          onLocationRequest(position.coords.latitude, position.coords.longitude);
          toast.success(t("geoSuccess"));
        }
      },
      (error: GeolocationPositionError) => {
        // Safari-compatible error handling - try multiple ways to access error code
        let errorCode: number | undefined;

        // Try direct access first
        try {
          errorCode = error.code;
        } catch {
          // If direct access fails, try alternative methods
          try {
            const err = error as Record<string, unknown> & {
              code?: number;
              message?: string;
              PERMISSION_DENIED?: number;
              POSITION_UNAVAILABLE?: number;
              TIMEOUT?: number;
            };
            if (typeof err === "object" && err !== null) {
              // Try accessing code property
              errorCode = err.code;
              // If that doesn't work, try PERMISSION_DENIED, POSITION_UNAVAILABLE, TIMEOUT constants
              if (errorCode === undefined) {
                if (err.PERMISSION_DENIED === 1 || err.message?.toLowerCase().includes("permission")) {
                  errorCode = 1;
                } else if (err.POSITION_UNAVAILABLE === 2 || err.message?.toLowerCase().includes("unavailable")) {
                  errorCode = 2;
                } else if (err.TIMEOUT === 3 || err.message?.toLowerCase().includes("timeout")) {
                  errorCode = 3;
                }
              }
            }
          } catch (e2) {
            // If all else fails, we'll use a generic message
            console.error("Could not extract error code:", e2);
          }
        }

        console.error("Geolocation error - code:", errorCode, "error object:", error);
        setIsGettingLocation(false);

        // Create a proper error object with the code we extracted
        const errorWithCode =
          errorCode !== undefined ? ({ ...error, code: errorCode } as GeolocationPositionError) : error;

        toast.error(getErrorMessage(errorWithCode));
      },
      {
        enableHighAccuracy: false,
        timeout: 15000, // Increased timeout for Safari
        maximumAge: 300000, // 5 minutes - Safari works better with cached positions
      },
    );
  };

  return (
    <div className="relative">
      <Input
        id={name}
        type="number"
        value={text}
        onFocus={() => setIsFocused(true)}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
          const val = e.target.value;
          setText(val);
          // Don't commit intermediate / non-numeric states upstream while
          // the user is typing. The displayed value (the local buffer)
          // still reflects exactly what they typed; we just defer parsing
          // until the value is unambiguously a number or empty.
          if (val === "") {
            onChange(undefined);
            return;
          }
          const parsed = property.type === "integer" ? parseInt(val, 10) : parseFloat(val);
          if (!Number.isNaN(parsed) && /^-?\d+(\.\d+)?$/.test(val)) {
            onChange(parsed);
          }
        }}
        onBlur={() => {
          setIsFocused(false);
          // Finalize on blur: empty -> undefined, otherwise parse and snap
          // the displayed text to the canonical numeric form. Invalid
          // partial input (e.g. just "-") is treated as cleared.
          if (text === "") {
            onChange(undefined);
            return;
          }
          const parsed = property.type === "integer" ? parseInt(text, 10) : parseFloat(text);
          if (Number.isNaN(parsed)) {
            onChange(undefined);
            setText("");
          } else {
            onChange(parsed);
            setText(String(parsed));
          }
        }}
        placeholder={property["ui:placeholder"] || property.description}
        min={property.minimum}
        max={property.maximum}
        disabled={disabled}
        required={required}
        className={showLocationButton ? "pr-10" : undefined}
      />
      {showLocationButton && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
          onClick={handleLocationClick}
          disabled={disabled || isGettingLocation || (isLocationLoading ?? false)}
          tabIndex={-1}
          title={t("useMyCurrentLocation")}
        >
          {isGettingLocation || isLocationLoading ? (
            <Loader2 className="h-4 w-4 text-muted-foreground animate-spin" />
          ) : (
            <MapPin className="h-4 w-4 text-muted-foreground" />
          )}
        </Button>
      )}
    </div>
  );
}

function BooleanField({ name, value, onChange, disabled }: FieldProps) {
  return <Switch id={name} checked={Boolean(value)} onCheckedChange={onChange} disabled={disabled} />;
}

/** WSF route options for the route picker (id matches WSDOT API route_id) */
const WSDOT_FERRY_ROUTES = [
  { id: 1, label: "Seattle – Bainbridge Island" },
  { id: 2, label: "Seattle – Bremerton" },
  { id: 3, label: "Fauntleroy – Vashon – Southworth" },
  { id: 4, label: "Point Defiance – Tahlequah" },
  { id: 5, label: "Anacortes – San Juan Islands" },
  { id: 6, label: "Anacortes – Sidney B.C." },
  { id: 7, label: "Mukilteo – Clinton" },
  { id: 8, label: "Port Townsend – Keystone" },
  { id: 9, label: "Edmonds – Kingston" },
] as const;

interface WsdotRoutePickerProps extends FieldProps {
  maxItems?: number;
}

function WsdotRoutePicker({
  name,
  property: _property,
  value,
  onChange,
  disabled,
  maxItems = 4,
}: WsdotRoutePickerProps) {
  const t = useTranslations("schemaForm");
  const items = Array.isArray(value) ? value : [];
  const routeEntries = items.map((item) =>
    item && typeof item === "object" && "route_id" in item ? Number((item as { route_id: number }).route_id) : 0,
  );

  const setRouteAt = (index: number, routeId: number) => {
    const next = [...routeEntries];
    next[index] = routeId;
    onChange(next.map((id) => ({ route_id: id })));
  };

  const handleAdd = () => {
    const firstId = WSDOT_FERRY_ROUTES[0]?.id ?? 1;
    onChange([...items, { route_id: firstId }]);
  };

  const handleRemove = (index: number) => {
    const next = items.filter((_, i) => i !== index) as { route_id: number }[];
    onChange(next);
  };

  const canAdd = routeEntries.length < maxItems;
  const canRemove = routeEntries.length > 0;

  return (
    <div className="space-y-3">
      {routeEntries.map((routeId, index) => (
        <div key={index} className="flex gap-2 items-center">
          <Select
            value={
              routeId && WSDOT_FERRY_ROUTES.some((r) => r.id === routeId)
                ? String(routeId)
                : String(WSDOT_FERRY_ROUTES[0]?.id ?? "")
            }
            onValueChange={(val) => setRouteAt(index, parseInt(val, 10))}
            disabled={disabled}
          >
            <SelectTrigger id={`${name}-${index}`} className="flex-1">
              <SelectValue placeholder={t("selectFerryRoute")} />
            </SelectTrigger>
            <SelectContent>
              {WSDOT_FERRY_ROUTES.map((route) => (
                <SelectItem key={route.id} value={String(route.id)}>
                  {route.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {canRemove && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => handleRemove(index)}
              disabled={disabled}
              className="h-9 w-9 shrink-0 text-destructive hover:text-destructive"
              aria-label={t("removeRoute")}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      ))}
      {canAdd && (
        <Button type="button" variant="outline" size="sm" onClick={handleAdd} disabled={disabled} className="w-full">
          <Plus className="h-4 w-4 mr-2" />
          {t("addFerryRoute")}
        </Button>
      )}
    </div>
  );
}

// Disney Park Queue Times picker: display names, store park_id and ride_ids
interface ParkRideEntry {
  park_id: number;
  ride_ids: number[];
}

type DisneyParksTimesPickerProps = FieldProps;

function DisneyParksTimesPicker({ name, value, onChange, disabled }: DisneyParksTimesPickerProps) {
  const t = useTranslations("schemaForm");
  const [parks, setParks] = useState<QueueTimesPark[]>([]);
  const [parksLoading, setParksLoading] = useState(true);
  const [ridesByParkId, setRidesByParkId] = useState<Record<number, QueueTimesRide[]>>({});

  const items = (Array.isArray(value) ? value : []) as ParkRideEntry[];

  const ensureRidesForPark = useCallback((parkId: number) => {
    setRidesByParkId((prev) => {
      if (prev[parkId] !== undefined) return prev;
      api
        .getQueueTimesRides(parkId)
        .then((data) => {
          setRidesByParkId((p) => ({ ...p, [parkId]: data }));
        })
        .catch(() => {
          setRidesByParkId((p) => ({ ...p, [parkId]: [] }));
        });
      return prev;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .getQueueTimesParks()
      .then((data) => {
        if (!cancelled) {
          setParks(data);
          setParksLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setParksLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    items.forEach((entry) => {
      if (entry?.park_id) ensureRidesForPark(entry.park_id);
    });
  }, [items, ensureRidesForPark]);

  const setEntryAt = (index: number, next: ParkRideEntry) => {
    const nextItems = [...items];
    nextItems[index] = next;
    onChange(nextItems);
  };

  const setParkAt = (index: number, parkId: number) => {
    setEntryAt(index, { park_id: parkId, ride_ids: [] });
    ensureRidesForPark(parkId);
  };

  const setRidesAt = (index: number, rideIds: number[]) => {
    setEntryAt(index, { ...items[index], ride_ids: rideIds });
  };

  const addRideAt = (index: number, rideId: number) => {
    const entry = items[index];
    if (!entry || entry.ride_ids.includes(rideId)) return;
    setRidesAt(index, [...entry.ride_ids, rideId]);
  };

  const removeRideAt = (index: number, rideIndex: number) => {
    const entry = items[index];
    if (!entry) return;
    const next = entry.ride_ids.filter((_, i) => i !== rideIndex);
    setRidesAt(index, next);
  };

  const handleAddPark = () => {
    const firstId = parks[0]?.id ?? 0;
    onChange([...items, { park_id: firstId, ride_ids: [] }]);
    if (firstId) ensureRidesForPark(firstId);
  };

  const handleRemovePark = (index: number) => {
    onChange(items.filter((_, i) => i !== index));
  };

  const _parkName = (id: number) => parks.find((p) => p.id === id)?.name ?? `Park ${id}`;
  const rideName = (parkId: number, rideId: number) =>
    ridesByParkId[parkId]?.find((r) => r.id === rideId)?.name ?? `Ride ${rideId}`;

  if (parksLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t("loadingParks")}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {items.map((entry, index) => (
        <div key={index} className="rounded-lg border p-3 space-y-2">
          <div className="flex gap-2 items-center">
            <Select
              value={entry.park_id ? String(entry.park_id) : ""}
              onValueChange={(val) => setParkAt(index, parseInt(val, 10))}
              disabled={disabled}
            >
              <SelectTrigger id={`${name}-park-${index}`} className="flex-1">
                <SelectValue placeholder={t("selectPark")} />
              </SelectTrigger>
              <SelectContent>
                {parks.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => handleRemovePark(index)}
              disabled={disabled}
              className="h-9 w-9 shrink-0 text-destructive hover:text-destructive"
              aria-label={t("removePark")}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
          {entry.park_id > 0 && (
            <>
              <div className="text-xs text-muted-foreground">{t("ridesByName")}</div>
              <div className="flex flex-wrap gap-1">
                {(entry.ride_ids || []).map((rid, rideIndex) => (
                  <span key={rid} className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-sm">
                    {rideName(entry.park_id, rid)}
                    <button
                      type="button"
                      onClick={() => removeRideAt(index, rideIndex)}
                      disabled={disabled}
                      className="rounded hover:bg-muted-foreground/20"
                      aria-label={t("removeRide")}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
              <Select value="" onValueChange={(val) => addRideAt(index, parseInt(val, 10))} disabled={disabled}>
                <SelectTrigger className="w-full max-w-xs">
                  <SelectValue placeholder={t("addRide")} />
                </SelectTrigger>
                <SelectContent>
                  {(ridesByParkId[entry.park_id] ?? [])
                    .filter((r) => !(entry.ride_ids || []).includes(r.id))
                    .map((r) => (
                      <SelectItem key={r.id} value={String(r.id)}>
                        {r.name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </>
          )}
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={handleAddPark} disabled={disabled} className="w-full">
        <Plus className="h-4 w-4 mr-2" />
        {t("addPark")}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Generic Data — interactive mapping helper
// ---------------------------------------------------------------------------

interface JsonTreeNodeProps {
  data: unknown;
  path: string;
  onSelect: (path: string, value: unknown) => void;
  defaultExpanded?: boolean;
}

function JsonTreeNode({ data, path, onSelect, defaultExpanded = false }: JsonTreeNodeProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    onSelect(path, data);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (data === null || data === undefined) {
    return <span className="text-muted-foreground italic text-xs">null</span>;
  }

  if (typeof data === "object" && !Array.isArray(data)) {
    const entries = Object.entries(data as Record<string, unknown>);
    return (
      <div className="ml-1">
        <button
          type="button"
          className="flex items-center gap-1 text-xs hover:bg-muted/60 rounded px-1 py-0.5 -ml-1 w-full text-left"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
          <span className="text-muted-foreground">{`{${entries.length}}`}</span>
        </button>
        {expanded && (
          <div className="ml-3 border-l border-border pl-2 space-y-0.5">
            {entries.map(([key, val]) => {
              const childPath = path ? `${path}.${key}` : key;
              const isLeaf = val === null || val === undefined || typeof val !== "object";
              return (
                <div key={key} className="flex items-start gap-1">
                  <span className="text-xs font-medium text-blue-600 dark:text-blue-400 shrink-0 pt-0.5">{key}:</span>
                  {isLeaf ? (
                    <div className="flex items-center gap-1 group min-w-0">
                      <span className="text-xs truncate">{String(val ?? "null")}</span>
                      <button
                        type="button"
                        onClick={handleCopy.bind(null, { stopPropagation: () => {} } as React.MouseEvent)}
                        onClickCapture={(e) => {
                          e.stopPropagation();
                          onSelect(childPath, val);
                          setCopied(true);
                          setTimeout(() => setCopied(false), 1500);
                        }}
                        className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 rounded hover:bg-muted"
                        title={`Use path: ${childPath}`}
                      >
                        {copied ? (
                          <Check className="h-3 w-3 text-green-600" />
                        ) : (
                          <Copy className="h-3 w-3 text-muted-foreground" />
                        )}
                      </button>
                    </div>
                  ) : (
                    <JsonTreeNode data={val} path={childPath} onSelect={onSelect} />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  if (Array.isArray(data)) {
    return (
      <div className="ml-1">
        <button
          type="button"
          className="flex items-center gap-1 text-xs hover:bg-muted/60 rounded px-1 py-0.5 -ml-1 w-full text-left"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
          <span className="text-muted-foreground">{`[${data.length}]`}</span>
        </button>
        {expanded && (
          <div className="ml-3 border-l border-border pl-2 space-y-0.5">
            {data.map((item, idx) => {
              const childPath = path ? `${path}[${idx}]` : `[${idx}]`;
              const isLeaf = item === null || item === undefined || typeof item !== "object";
              return (
                <div key={idx} className="flex items-start gap-1">
                  <span className="text-xs font-medium text-purple-600 dark:text-purple-400 shrink-0 pt-0.5">
                    [{idx}]:
                  </span>
                  {isLeaf ? (
                    <div className="flex items-center gap-1 group min-w-0">
                      <span className="text-xs truncate">{String(item ?? "null")}</span>
                      <button
                        type="button"
                        onClickCapture={(e) => {
                          e.stopPropagation();
                          onSelect(childPath, item);
                        }}
                        className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 rounded hover:bg-muted"
                        title={`Use path: ${childPath}`}
                      >
                        <Copy className="h-3 w-3 text-muted-foreground" />
                      </button>
                    </div>
                  ) : (
                    <JsonTreeNode data={item} path={childPath} onSelect={onSelect} />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return <span className="text-xs">{String(data)}</span>;
}

interface MappingEntry {
  variable?: string;
  path?: string;
  default?: string;
}

interface GenericDataMappingHelperProps extends FieldProps {
  allValues: Record<string, unknown>;
}

function GenericDataMappingHelper({
  name: _name,
  property: _property,
  value,
  onChange,
  disabled,
  allValues,
}: GenericDataMappingHelperProps) {
  const t = useTranslations("schemaForm");
  const [previewData, setPreviewData] = useState<unknown>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const mappings = (Array.isArray(value) ? value : []) as MappingEntry[];

  const handleFetchPreview = async () => {
    const url = (allValues.url as string) || "";
    if (!url) {
      toast.error(t("enterDataUrlFirst"));
      return;
    }

    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewData(null);
    try {
      const result = await api.genericDataTestFetch({
        url,
        format: (allValues.format as string) || "json",
        method: (allValues.method as string) || "GET",
        headers: (allValues.headers as { name: string; value: string }[]) || [],
        body: (allValues.body as string) || undefined,
      });
      setPreviewData(result.data);
      toast.success(t("dataFetched"));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setPreviewError(msg);
      toast.error(t("fetchFailed", { error: msg }));
    } finally {
      setPreviewLoading(false);
    }
  };

  const handlePathSelect = (path: string, _val: unknown) => {
    const varName =
      path
        .split(".")
        .pop()
        ?.replace(/\[\d+\]/g, "") || "value";
    const sanitised =
      varName
        .toLowerCase()
        .replace(/[^a-z0-9_]/g, "_")
        .replace(/^_+|_+$/g, "") || "value";
    const existing = new Set(mappings.map((m) => m.variable));
    let finalVar = sanitised;
    let counter = 2;
    while (existing.has(finalVar)) {
      finalVar = `${sanitised}_${counter++}`;
    }
    const newMappings = [...mappings, { variable: finalVar, path, default: "" }];
    onChange(newMappings);
    toast.success(t("addedMapping", { variable: finalVar, path }));
  };

  const handleAdd = () => {
    onChange([...mappings, { variable: "", path: "", default: "" }]);
  };

  const handleRemove = (index: number) => {
    onChange(mappings.filter((_, i) => i !== index));
  };

  const handleItemChange = (index: number, key: string, val: string) => {
    const next = [...mappings];
    next[index] = { ...next[index], [key]: val };
    onChange(next);
  };

  const resolvePreview = (path: string): string | null => {
    if (!previewData || !path) return null;
    try {
      const segments = path.split(".");
      let current: unknown = previewData;
      for (const segment of segments) {
        if (current === null || current === undefined) return null;
        const match = segment.match(/^([^\[]*)\[(\d+)\]$/);
        if (match) {
          const [, key, idxStr] = match;
          if (key && typeof current === "object" && !Array.isArray(current)) {
            current = (current as Record<string, unknown>)[key];
          }
          if (Array.isArray(current)) {
            current = current[parseInt(idxStr, 10)];
          } else {
            return null;
          }
        } else {
          if (typeof current === "object" && !Array.isArray(current) && current !== null) {
            current = (current as Record<string, unknown>)[segment];
          } else {
            return null;
          }
        }
      }
      return current !== null && current !== undefined ? String(current) : null;
    } catch {
      return null;
    }
  };

  return (
    <div className="space-y-4">
      {/* Test & Preview button */}
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleFetchPreview}
          disabled={disabled || previewLoading}
          className="gap-1.5"
        >
          {previewLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
          {t("testAndPreview")}
        </Button>
        <p className="text-xs text-muted-foreground self-center">{t("testAndPreviewHelp")}</p>
      </div>

      {/* Preview error */}
      {previewError && <div className="text-xs text-destructive bg-destructive/10 rounded-md p-2">{previewError}</div>}

      {/* Response tree browser */}
      {previewData && (
        <div className="border rounded-lg p-3 bg-muted/20 sm:max-h-64 sm:overflow-auto">
          <div className="text-xs font-medium text-muted-foreground mb-2">{t("responseClickToAdd")}</div>
          <JsonTreeNode data={previewData} path="" onSelect={handlePathSelect} defaultExpanded={true} />
        </div>
      )}

      {/* Mapping rows */}
      {mappings.map((mapping, index) => {
        const preview = resolvePreview(mapping.path || "");
        return (
          <div key={index} className="flex gap-2">
            <div className="flex-1 grid gap-2 p-3 border rounded-lg bg-muted/30">
              <div className="grid grid-cols-2 gap-2">
                <div className="grid gap-1">
                  <Label htmlFor={`mapping-${index}-variable`} className="text-xs">
                    {t("variableName")}
                  </Label>
                  <Input
                    id={`mapping-${index}-variable`}
                    value={mapping.variable || ""}
                    onChange={(e) => handleItemChange(index, "variable", e.target.value)}
                    placeholder={t("variableNamePlaceholder")}
                    disabled={disabled}
                    className="h-8 text-sm"
                  />
                </div>
                <div className="grid gap-1">
                  <Label htmlFor={`mapping-${index}-path`} className="text-xs">
                    {t("dataPath")}
                  </Label>
                  <Input
                    id={`mapping-${index}-path`}
                    value={mapping.path || ""}
                    onChange={(e) => handleItemChange(index, "path", e.target.value)}
                    placeholder={t("dataPathPlaceholder")}
                    disabled={disabled}
                    className="h-8 text-sm"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="grid gap-1">
                  <Label htmlFor={`mapping-${index}-default`} className="text-xs">
                    {t("defaultValue")}
                  </Label>
                  <Input
                    id={`mapping-${index}-default`}
                    value={mapping.default || ""}
                    onChange={(e) => handleItemChange(index, "default", e.target.value)}
                    placeholder={t("defaultValuePlaceholder")}
                    disabled={disabled}
                    className="h-8 text-sm"
                  />
                </div>
                {preview !== null && (
                  <div className="grid gap-1">
                    <Label className="text-xs text-green-700 dark:text-green-400">{t("preview")}</Label>
                    <div className="h-8 flex items-center text-sm text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-950/30 rounded-md px-2 truncate border border-green-200 dark:border-green-800">
                      {preview}
                    </div>
                  </div>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                {t("useInTemplates")}{" "}
                <code className="bg-muted px-1 rounded">
                  {"{{"}generic_data.{mapping.variable || "..."}
                  {"}}"}
                </code>
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => handleRemove(index)}
              disabled={disabled}
              className="h-9 w-9 text-destructive hover:text-destructive self-start mt-3"
              aria-label={t("removeMapping")}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        );
      })}

      <Button type="button" variant="outline" size="sm" onClick={handleAdd} disabled={disabled} className="w-full">
        <Plus className="h-4 w-4 mr-2" />
        {t("addMapping")}
      </Button>
    </div>
  );
}

interface ArrayFieldProps extends FieldProps {
  itemSchema: SchemaProperty;
}

function ArrayField({ name, property, value, onChange, disabled, itemSchema }: ArrayFieldProps) {
  const t = useTranslations("schemaForm");
  const rawItems = Array.isArray(value) ? value : [];

  // Track items with stable IDs so React doesn't reuse component instances
  // when items are added or removed — index-based keys cause Radix UI portal
  // cleanup to call removeChild on a detached node.
  const nextId = useRef(0);
  const [keyed, setKeyed] = useState<{ id: number; value: unknown }[]>(() =>
    rawItems.map((v) => ({ id: nextId.current++, value: v })),
  );

  // Keep keyed list in sync when the parent value changes from outside
  // (e.g. initial load or external reset), but only when the item count changes
  // so we don't thrash the IDs on every keystroke.
  useEffect(() => {
    if (rawItems.length !== keyed.length) {
      setKeyed(rawItems.map((v) => ({ id: nextId.current++, value: v })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rawItems.length]);

  const handleAdd = () => {
    let defaultValue: unknown;
    if (itemSchema.type === "object") {
      defaultValue = {};
    } else if (itemSchema.type === "string") {
      defaultValue = "";
    } else if (itemSchema.type === "number" || itemSchema.type === "integer") {
      defaultValue = 0;
    } else if (itemSchema.type === "boolean") {
      defaultValue = false;
    } else {
      defaultValue = null;
    }
    const newEntry = { id: nextId.current++, value: defaultValue };
    const next = [...keyed, newEntry];
    setKeyed(next);
    onChange(next.map((k) => k.value));
  };

  const handleRemove = (index: number) => {
    const next = keyed.filter((_, i) => i !== index);
    setKeyed(next);
    onChange(next.map((k) => k.value));
  };

  const handleItemChange = (index: number, newValue: unknown) => {
    const next = keyed.map((k, i) => (i === index ? { ...k, value: newValue } : k));
    setKeyed(next);
    onChange(next.map((k) => k.value));
  };

  const canAdd = !property.maxItems || keyed.length < property.maxItems;
  const canRemove = !property.minItems || keyed.length > property.minItems;

  return (
    <div className="space-y-3">
      {keyed.map(({ id, value: item }, index) => (
        <div key={id} className="flex gap-2">
          <div className="flex-1">
            {itemSchema.type === "object" && itemSchema.properties ? (
              <div className="grid gap-3 p-3 border rounded-lg bg-muted/30">
                {Object.entries(itemSchema.properties).map(([key, propSchema]) => (
                  <div key={key} className="grid gap-1.5">
                    <Label htmlFor={`${name}-${index}-${key}`} className="text-xs">
                      {propSchema.title || key}
                    </Label>
                    <FormField
                      name={`${name}-${index}-${key}`}
                      property={propSchema}
                      value={(item as Record<string, unknown>)?.[key]}
                      onChange={(val) => {
                        const newItem = { ...(item as Record<string, unknown>), [key]: val };
                        handleItemChange(index, newItem);
                      }}
                      disabled={disabled}
                      onLocationRequest={undefined}
                      showLocationButton={false}
                      isLocationLoading={false}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <FormField
                name={`${name}-${index}`}
                property={itemSchema}
                value={item}
                onChange={(val) => handleItemChange(index, val)}
                disabled={disabled}
              />
            )}
          </div>
          {canRemove && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => handleRemove(index)}
              disabled={disabled}
              className="h-9 w-9 text-destructive hover:text-destructive"
              aria-label={t("removeItem")}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      ))}

      {canAdd && (
        <Button type="button" variant="outline" size="sm" onClick={handleAdd} disabled={disabled} className="w-full">
          <Plus className="h-4 w-4 mr-2" />
          Add {property.title || name}
        </Button>
      )}
    </div>
  );
}

interface FormFieldProps extends FieldProps {
  onLocationRequest?: (lat: number, lon: number) => void;
  showLocationButton?: boolean;
  isLocationLoading?: boolean;
  allValues?: Record<string, unknown>;
}

function FormField({
  name,
  property,
  value,
  onChange,
  required,
  disabled,
  onLocationRequest,
  showLocationButton,
  isLocationLoading,
  allValues,
}: FormFieldProps) {
  const t = useTranslations("schemaForm");
  switch (property.type) {
    case "string":
      return (
        <StringField
          name={name}
          property={property}
          value={value}
          onChange={onChange}
          required={required}
          disabled={disabled}
        />
      );
    case "number":
    case "integer":
      return (
        <NumberField
          name={name}
          property={property}
          value={value}
          onChange={onChange}
          required={required}
          disabled={disabled}
          onLocationRequest={onLocationRequest}
          showLocationButton={showLocationButton}
          isLocationLoading={isLocationLoading}
        />
      );
    case "boolean":
      return (
        <BooleanField
          name={name}
          property={property}
          value={value}
          onChange={onChange}
          required={required}
          disabled={disabled}
        />
      );
    case "array":
      if (property["ui:widget"] === "generic-data-mapping-helper" && property.items) {
        return (
          <GenericDataMappingHelper
            name={name}
            property={property}
            value={value}
            onChange={onChange}
            required={required}
            disabled={disabled}
            allValues={allValues || {}}
          />
        );
      }
      if (property["ui:widget"] === "wsdot-route-picker" && property.items) {
        return (
          <WsdotRoutePicker
            name={name}
            property={property}
            value={value}
            onChange={onChange}
            required={required}
            disabled={disabled}
            maxItems={property.maxItems ?? 4}
          />
        );
      }
      if (property["ui:widget"] === "disney-parks-times-picker") {
        return (
          <DisneyParksTimesPicker
            name={name}
            property={property}
            value={value}
            onChange={onChange}
            required={required}
            disabled={disabled}
          />
        );
      }
      if (property.items) {
        return (
          <ArrayField
            name={name}
            property={property}
            value={value}
            onChange={onChange}
            required={required}
            disabled={disabled}
            itemSchema={property.items}
          />
        );
      }
      return <div className="text-sm text-muted-foreground">{t("arrayTypeNoItems")}</div>;
    case "object":
      if (property.properties) {
        return (
          <div className="grid gap-4 p-4 border rounded-lg">
            {Object.entries(property.properties).map(([key, propSchema]) => (
              <div key={key} className="grid gap-1.5">
                <Label htmlFor={`${name}-${key}`}>
                  {propSchema.title || key}
                  {property.required?.includes(key) && <span className="text-destructive ml-1">*</span>}
                </Label>
                <FormField
                  name={`${name}-${key}`}
                  property={propSchema}
                  value={(value as Record<string, unknown>)?.[key]}
                  onChange={(val) => {
                    const newValue = { ...(value as Record<string, unknown>), [key]: val };
                    onChange(newValue);
                  }}
                  required={property.required?.includes(key)}
                  disabled={disabled}
                  onLocationRequest={undefined}
                  showLocationButton={false}
                  isLocationLoading={false}
                />
                {propSchema.description && <p className="text-xs text-muted-foreground">{propSchema.description}</p>}
              </div>
            ))}
          </div>
        );
      }
      return <div className="text-sm text-muted-foreground">{t("objectTypeNoProperties")}</div>;
    default:
      return <div className="text-sm text-muted-foreground">Unknown type: {property.type}</div>;
  }
}

/**
 * SchemaForm - Renders a form from a JSON Schema
 *
 * This component takes a JSON Schema and renders appropriate form fields
 * for each property. It supports:
 * - String fields (text, password, select, textarea)
 * - Number/Integer fields
 * - Boolean fields (switches)
 * - Array fields (add/remove items)
 * - Nested object fields
 */
export function SchemaForm({ schema, values, onChange, disabled, className }: SchemaFormProps) {
  const t = useTranslations("schemaForm");
  const handleFieldChange = useCallback(
    (fieldName: string, fieldValue: unknown) => {
      onChange({ ...values, [fieldName]: fieldValue });
    },
    [values, onChange],
  );

  // Check if both latitude and longitude fields exist
  const hasLatitude = schema.properties?.latitude !== undefined;
  const hasLongitude = schema.properties?.longitude !== undefined;
  const hasLocationFields = hasLatitude && hasLongitude;

  const handleLocationRequest = useCallback(
    (lat: number, lon: number) => {
      onChange({
        ...values,
        latitude: lat,
        longitude: lon,
      });
    },
    [values, onChange],
  );

  if (!schema.properties) {
    return <div className="text-sm text-muted-foreground">{t("noSchemaProperties")}</div>;
  }

  return (
    <div className={cn("grid gap-4", className)}>
      {Object.entries(schema.properties).map(([name, property]) => {
        // Skip the 'enabled' field as it's handled separately
        if (name === "enabled") return null;

        const isRequired = schema.required?.includes(name);
        const isLocationField = hasLocationFields && (name === "latitude" || name === "longitude");
        const showLocationButton = isLocationField && !!navigator.geolocation;

        // Disable digit_color when color_pattern is not "solid" (visual_clock plugin)
        const isDigitColorField = name === "digit_color";
        const colorPattern = values["color_pattern"] || schema.properties["color_pattern"]?.default || "solid";
        const shouldDisableDigitColor = isDigitColorField && colorPattern !== "solid";
        const fieldDisabled = disabled || shouldDisableDigitColor;

        return (
          <div key={name} className="grid gap-1.5">
            <Label htmlFor={name} className="flex items-center gap-1">
              {property.title || name}
              {isRequired && <span className="text-destructive">*</span>}
            </Label>
            <FormField
              name={name}
              property={property}
              value={values[name]}
              onChange={(val) => handleFieldChange(name, val)}
              required={isRequired}
              disabled={fieldDisabled}
              onLocationRequest={showLocationButton ? handleLocationRequest : undefined}
              showLocationButton={showLocationButton}
              isLocationLoading={false}
              allValues={values}
            />
            {property.description && <p className="text-xs text-muted-foreground">{property.description}</p>}
            {showLocationButton && <p className="text-xs text-muted-foreground">{t("clickLocationIcon")}</p>}
            {shouldDisableDigitColor && <p className="text-xs text-muted-foreground">{t("digitColorNotUsed")}</p>}
          </div>
        );
      })}
    </div>
  );
}

export type { JSONSchema, SchemaProperty };
