"use client";

import {
  Box,
  Button,
  Flex,
  Grid,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import { Eye, EyeOff, Loader2, MapPin, Plus, Trash2 } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { TimezonePicker } from "@/components/ui/timezone-picker";
import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

import { FieldScopeContext, SchemaFormPluginContext, useFieldScope } from "./field-context";
import { isJsonPathMapper, JsonPathMapperField, type JsonPathMapperUiOptions } from "./json-path-mapper-field";
import { PagePickerField } from "./page-picker-field";
import { RemoteOptionsField, type RemoteOptionsUiOptions } from "./remote-options-field";

// JSON Schema types (simplified for our use case)
interface SchemaProperty {
  type: "string" | "number" | "integer" | "boolean" | "array" | "object";
  title?: string;
  description?: string;
  default?: unknown;
  /**
   * Normally a JSON Schema `enum` array, but plugin manifests are
   * user-authored JSON: a bare string or an `{ values: [...] }` wrapper both
   * turn up in the wild, and StringField normalizes all three. Typed to match
   * what the runtime actually handles rather than the well-formed case only.
   */
  enum?: unknown[] | string | Record<string, unknown>;
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
  "ui:options"?: RemoteOptionsUiOptions & JsonPathMapperUiOptions;
}

interface JSONSchema {
  type: "object";
  properties: Record<string, SchemaProperty>;
  required?: string[];
}

/**
 * Narrow an untyped `settings_schema` blob (it arrives as raw manifest JSON
 * over the wire) to the subset this form reads. Only checked to the depth the
 * renderer relies on — individual field shapes are already handled
 * defensively by each widget.
 */
export function asJSONSchema(value: Record<string, unknown> | undefined | null): JSONSchema {
  const properties = value?.properties;
  const required = value?.required;
  return {
    type: "object",
    properties:
      properties && typeof properties === "object" && !Array.isArray(properties)
        ? (properties as Record<string, SchemaProperty>)
        : {},
    required: Array.isArray(required) ? required.filter((name): name is string => typeof name === "string") : undefined,
  };
}

/** Property name → its display title (falling back to the raw key). */
function titlesOf(properties: Record<string, SchemaProperty> | undefined): Record<string, string> {
  const titles: Record<string, string> = {};
  for (const [key, propSchema] of Object.entries(properties ?? {})) {
    titles[key] = propSchema.title || key;
  }
  return titles;
}

interface SchemaFormProps {
  schema: JSONSchema;
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
  disabled?: boolean;
  className?: string;
  /**
   * Id of the plugin whose settings are being edited. Optional so existing
   * call sites keep working; `remote-options` fields need it to know which
   * plugin to ask for a catalog and degrade to a disabled control without it.
   */
  pluginId?: string;
}

// Individual field components
interface FieldProps {
  name: string;
  property: SchemaProperty;
  value: unknown;
  /**
   * Commit this field's value, optionally together with a patch of *sibling*
   * properties in the same object.
   *
   * Only `remote-options` with `ui:options.labels_field` uses the second
   * argument, and it has to exist because the two writes are one edit:
   * removing a chosen row changes the array *and* drops that row's display
   * name. Two separate `onChange` calls in one handler would both be computed
   * from the same pre-edit object, so the second would silently undo the
   * first. Every other field ignores the argument and nothing changes for it.
   */
  onChange: (value: unknown, siblings?: Record<string, unknown>) => void;
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
    <Box className="relative">
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
    </Box>
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
    <Box className="relative">
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
    </Box>
  );
}

function BooleanField({ name, value, onChange, disabled }: FieldProps) {
  return <Switch id={name} checked={Boolean(value)} onCheckedChange={onChange} disabled={disabled} />;
}

interface ArrayFieldProps extends FieldProps {
  itemSchema: SchemaProperty;
}

function ArrayField({ name, property, value, onChange, disabled, itemSchema }: ArrayFieldProps) {
  const t = useTranslations("schemaForm");
  const { root } = useFieldScope();
  const rawItems = Array.isArray(value) ? value : [];

  // Track items with stable IDs so React doesn't reuse component instances
  // when items are added or removed — index-based keys cause Radix UI portal
  // cleanup to call removeChild on a detached node.
  //
  // `nextId` seeds from the initial item count rather than 0 so IDs assigned
  // later (handleAdd, the resync effect) never collide with the initial
  // index-based IDs below. The initial `keyed` state uses plain array
  // indices instead of `nextId.current++` because reading a ref's value
  // during render (even inside a useState lazy initializer, which runs
  // during the render phase) is unsound under Strict Mode / concurrent
  // rendering — refs must only be read in effects or event handlers.
  const nextId = useRef(rawItems.length);
  const [keyed, setKeyed] = useState<{ id: number; value: unknown }[]>(() =>
    rawItems.map((v, i) => ({ id: i, value: v })),
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
      // Seed every enum-typed property — required or not — with the value its
      // Select will display: the declared `default` when there is one, else the
      // first allowed value. Both render paths resolve the shown option that
      // way, so seeding anything else would persist something other than what
      // the user sees. The presence check must stay `!== undefined` so a
      // legitimate falsy default such as `0` or `""` is honoured.
      const seeded: Record<string, unknown> = {};
      for (const [key, propSchema] of Object.entries(itemSchema.properties ?? {})) {
        if (Array.isArray(propSchema.enum) && propSchema.enum.length > 0) {
          seeded[key] = propSchema.default !== undefined ? propSchema.default : propSchema.enum[0];
        }
      }
      defaultValue = seeded;
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
    <Stack gap="3">
      {keyed.map(({ id, value: item }, index) => (
        <Flex key={id} gap="2">
          <Box className="flex-1">
            {itemSchema.type === "object" && itemSchema.properties ? (
              // A field inside an array item names its siblings *within that
              // item*, so the item — not the whole config — is its scope.
              <FieldScopeContext.Provider
                value={{
                  scope: (item as Record<string, unknown>) ?? {},
                  root,
                  titles: titlesOf(itemSchema.properties),
                }}
              >
                <Grid gap="3" className="p-3 border rounded-lg bg-muted/30">
                  {Object.entries(itemSchema.properties).map(([key, propSchema]) => (
                    <Grid key={key} gap="1.5">
                      <Label htmlFor={`${name}-${index}-${key}`} className="text-xs">
                        {propSchema.title || key}
                      </Label>
                      <FormField
                        name={`${name}-${index}-${key}`}
                        property={propSchema}
                        value={(item as Record<string, unknown>)?.[key]}
                        onChange={(val, siblings) => {
                          const newItem = { ...(item as Record<string, unknown>), ...siblings, [key]: val };
                          handleItemChange(index, newItem);
                        }}
                        disabled={disabled}
                        onLocationRequest={undefined}
                        showLocationButton={false}
                        isLocationLoading={false}
                      />
                    </Grid>
                  ))}
                </Grid>
              </FieldScopeContext.Provider>
            ) : (
              <FormField
                name={`${name}-${index}`}
                property={itemSchema}
                value={item}
                onChange={(val) => handleItemChange(index, val)}
                disabled={disabled}
              />
            )}
          </Box>
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
        </Flex>
      ))}

      {canAdd && (
        <Button type="button" variant="outline" size="sm" onClick={handleAdd} disabled={disabled} className="w-full">
          <Plus className="h-4 w-4 mr-2" />
          Add {property.title || name}
        </Button>
      )}
    </Stack>
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
  const { root } = useFieldScope();

  // The generic remote-options widget serves every declared type — a scalar
  // field is single-select, an array field with `ui:options.multiple` is
  // multi-select — so it is dispatched ahead of the per-type switch. There is
  // deliberately only one widget name for this capability.
  if (property["ui:widget"] === "remote-options") {
    return <RemoteOptionsField name={name} property={property} value={value} onChange={onChange} disabled={disabled} />;
  }

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
      if (isJsonPathMapper(property["ui:widget"]) && property.items) {
        return (
          <JsonPathMapperField
            property={property}
            value={value}
            onChange={onChange}
            disabled={disabled}
            allValues={allValues || {}}
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
      return <Text tone="muted">{t("arrayTypeNoItems")}</Text>;
    case "object":
      if (property.properties) {
        return (
          // Same rule as an array item: a field in a nested object names its
          // siblings inside that object, so that object is its scope.
          <FieldScopeContext.Provider
            value={{
              scope: (value as Record<string, unknown>) ?? {},
              root,
              titles: titlesOf(property.properties),
            }}
          >
            <Grid gap="4" className="p-4 border rounded-lg">
              {Object.entries(property.properties).map(([key, propSchema]) => (
                <Grid key={key} gap="1.5">
                  <Label htmlFor={`${name}-${key}`}>
                    {propSchema.title || key}
                    {property.required?.includes(key) && (
                      <Text as="span" tone="destructive" className="ml-1">
                        *
                      </Text>
                    )}
                  </Label>
                  <FormField
                    name={`${name}-${key}`}
                    property={propSchema}
                    value={(value as Record<string, unknown>)?.[key]}
                    onChange={(val, siblings) => {
                      const newValue = { ...(value as Record<string, unknown>), ...siblings, [key]: val };
                      onChange(newValue);
                    }}
                    required={property.required?.includes(key)}
                    disabled={disabled}
                    onLocationRequest={undefined}
                    showLocationButton={false}
                    isLocationLoading={false}
                  />
                  {propSchema.description && (
                    <Text size="xs" tone="muted">
                      {propSchema.description}
                    </Text>
                  )}
                </Grid>
              ))}
            </Grid>
          </FieldScopeContext.Provider>
        );
      }
      return <Text tone="muted">{t("objectTypeNoProperties")}</Text>;
    default:
      return <Text tone="muted">Unknown type: {property.type}</Text>;
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
export function SchemaForm({ schema, values, onChange, disabled, className, pluginId }: SchemaFormProps) {
  const t = useTranslations("schemaForm");
  // Top-level fields resolve `depends_on` against the whole config: at this
  // depth the sibling scope and the root are the same object.
  const rootScope = React.useMemo(
    () => ({ scope: values, root: values, titles: titlesOf(schema.properties) }),
    [values, schema.properties],
  );
  const handleFieldChange = useCallback(
    (fieldName: string, fieldValue: unknown, siblings?: Record<string, unknown>) => {
      onChange({ ...values, ...siblings, [fieldName]: fieldValue });
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
    return <Text tone="muted">{t("noSchemaProperties")}</Text>;
  }

  return (
    <SchemaFormPluginContext.Provider value={pluginId ?? null}>
      <FieldScopeContext.Provider value={rootScope}>
        <Grid gap="4" className={className}>
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
              <Grid key={name} gap="1.5">
                <Label htmlFor={name} className="flex items-center gap-1">
                  {property.title || name}
                  {isRequired && (
                    <Text as="span" tone="destructive">
                      *
                    </Text>
                  )}
                </Label>
                <FormField
                  name={name}
                  property={property}
                  value={values[name]}
                  onChange={(val, siblings) => handleFieldChange(name, val, siblings)}
                  required={isRequired}
                  disabled={fieldDisabled}
                  onLocationRequest={showLocationButton ? handleLocationRequest : undefined}
                  showLocationButton={showLocationButton}
                  isLocationLoading={false}
                  allValues={values}
                />
                {property.description && (
                  <Text size="xs" tone="muted">
                    {property.description}
                  </Text>
                )}
                {showLocationButton && (
                  <Text size="xs" tone="muted">
                    {t("clickLocationIcon")}
                  </Text>
                )}
                {shouldDisableDigitColor && (
                  <Text size="xs" tone="muted">
                    {t("digitColorNotUsed")}
                  </Text>
                )}
              </Grid>
            );
          })}
        </Grid>
      </FieldScopeContext.Provider>
    </SchemaFormPluginContext.Provider>
  );
}

export type { JSONSchema, SchemaProperty };
