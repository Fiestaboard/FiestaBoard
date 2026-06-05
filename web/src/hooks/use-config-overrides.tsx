"use client";

import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useState } from "react";

// Service keys that can be toggled
export type ServiceKey =
  | "datetime_enabled"
  | "weather_enabled"
  | "home_assistant_enabled"
  | "guest_wifi_enabled"
  | "star_trek_quotes_enabled"
  | "rotation_enabled";

export const SERVICE_KEYS: ServiceKey[] = [
  "datetime_enabled",
  "weather_enabled",
  "home_assistant_enabled",
  "guest_wifi_enabled",
  "star_trek_quotes_enabled",
  "rotation_enabled",
];

type Overrides = Record<ServiceKey, boolean | null>;

interface ConfigOverridesContextValue {
  overrides: Overrides;
  setOverride: (key: ServiceKey, value: boolean | null) => void;
  resetOverrides: () => void;
  getEffectiveValue: (key: ServiceKey, backendValue: boolean) => boolean;
  isOverridden: (key: ServiceKey) => boolean;
  // For API calls - returns only the overridden values
  getActiveOverrides: () => Partial<Record<ServiceKey, boolean>>;
}

const defaultOverrides: Overrides = {
  datetime_enabled: null,
  weather_enabled: null,
  home_assistant_enabled: null,
  guest_wifi_enabled: null,
  star_trek_quotes_enabled: null,
  rotation_enabled: null,
};

const ConfigOverridesContext = createContext<ConfigOverridesContextValue | null>(null);

export function ConfigOverridesProvider({ children }: { children: ReactNode }) {
  const [overrides, setOverrides] = useState<Overrides>(defaultOverrides);

  const setOverride = useCallback((key: ServiceKey, value: boolean | null) => {
    setOverrides((prev) => ({ ...prev, [key]: value }));
  }, []);

  const resetOverrides = useCallback(() => {
    setOverrides(defaultOverrides);
  }, []);

  const getEffectiveValue = useCallback(
    (key: ServiceKey, backendValue: boolean): boolean => {
      const override = overrides[key];
      return override !== null ? override : backendValue;
    },
    [overrides],
  );

  const isOverridden = useCallback(
    (key: ServiceKey): boolean => {
      return overrides[key] !== null;
    },
    [overrides],
  );

  const getActiveOverrides = useCallback((): Partial<Record<ServiceKey, boolean>> => {
    const active: Partial<Record<ServiceKey, boolean>> = {};
    for (const key of SERVICE_KEYS) {
      if (overrides[key] !== null) {
        active[key] = overrides[key] as boolean;
      }
    }
    return active;
  }, [overrides]);

  return (
    <ConfigOverridesContext.Provider
      value={{
        overrides,
        setOverride,
        resetOverrides,
        getEffectiveValue,
        isOverridden,
        getActiveOverrides,
      }}
    >
      {children}
    </ConfigOverridesContext.Provider>
  );
}

export function useConfigOverrides() {
  const context = useContext(ConfigOverridesContext);
  if (!context) {
    throw new Error("useConfigOverrides must be used within ConfigOverridesProvider");
  }
  return context;
}
