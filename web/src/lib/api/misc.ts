// Misc domain: legacy display endpoints and per-plugin helper
// endpoints (Bay Wheels, Muni, traffic, stocks, generic data).

import { fetchApi } from "./core";
import type { ActionResponse } from "./shared";

export interface PreviewResponse {
  message: string;
  lines: string[];
  display_type: string;
  line_count: number;
  preview: boolean;
}

// Display types
export interface DisplayInfo {
  type: string;
  available: boolean;
  description: string;
}

export interface DisplaysResponse {
  displays: DisplayInfo[];
  total: number;
  available_count: number;
}

export interface DisplayResponse {
  display_type: string;
  message: string;
  lines: string[];
  line_count: number;
  available: boolean;
}

export interface DisplayRawResponse {
  display_type: string;
  data: Record<string, unknown>;
  available: boolean;
  error: string | null;
}

export interface DisplayRawBatchResponse {
  displays: Record<
    string,
    {
      data: Record<string, unknown>;
      available: boolean;
      error: string | null;
    }
  >;
  total: number;
  successful: number;
}

// Utility types for API helper endpoints (station finder, stop finder, etc.)
export interface MuniStop {
  stop_code: string;
  stop_id: string;
  name: string;
  lat: number | null;
  lon: number | null;
  distance_km?: number;
  routes?: string[];
}

export interface BayWheelsStation {
  station_id: string;
  name: string;
  lat?: number;
  lon?: number;
  address?: string;
  capacity?: number;
  distance_km?: number;
  num_bikes_available?: number;
  electric_bikes?: number;
  classic_bikes?: number;
  num_docks_available?: number;
  is_renting?: boolean;
}

export interface TrafficRoute {
  origin: string;
  destination: string;
  destination_name: string;
}

export interface StockSymbol {
  symbol: string;
  name: string;
}

export interface StockSymbolValidation {
  valid: boolean;
  symbol: string;
  name?: string;
  error?: string;
}

export const miscApi = {
  // Display endpoints
  getDisplays: () => fetchApi<DisplaysResponse>("/displays"),
  getDisplay: (type: string) => fetchApi<DisplayResponse>(`/displays/${type}`),
  getDisplayRaw: (type: string) => fetchApi<DisplayRawResponse>(`/displays/${type}/raw`),
  getDisplaysRawBatch: (displayTypes: string[], enabledOnly?: boolean) =>
    fetchApi<DisplayRawBatchResponse>("/displays/raw/batch", {
      method: "POST",
      body: JSON.stringify({
        display_types: displayTypes,
        enabled_only: enabledOnly ?? true,
      }),
    }),
  sendDisplay: (type: string, target?: "ui" | "board" | "both") => {
    const params = target ? `?target=${target}` : "";
    return fetchApi<ActionResponse>(`/displays/${type}/send${params}`, { method: "POST" });
  },
  // Bay Wheels station search endpoints
  listBayWheelsStations: () => fetchApi<{ stations: BayWheelsStation[]; total: number }>("/baywheels/stations"),
  findNearbyBayWheelsStations: (lat: number, lng: number, radius?: number, limit?: number) => {
    const params = new URLSearchParams({
      lat: lat.toString(),
      lng: lng.toString(),
      ...(radius !== undefined && { radius: radius.toString() }),
      ...(limit !== undefined && { limit: limit.toString() }),
    });
    return fetchApi<{
      stations: BayWheelsStation[];
      count: number;
      search_location: { lat: number; lng: number };
      radius_km: number;
    }>(`/baywheels/stations/nearby?${params}`);
  },
  searchBayWheelsStationsByAddress: (address: string, radius?: number, limit?: number) => {
    const params = new URLSearchParams({
      address,
      ...(radius !== undefined && { radius: radius.toString() }),
      ...(limit !== undefined && { limit: limit.toString() }),
    });
    return fetchApi<{
      stations: BayWheelsStation[];
      count: number;
      search_address: string;
      geocoded_location: { lat: number; lng: number; display_name: string };
      radius_km: number;
    }>(`/baywheels/stations/search?${params}`);
  },

  // MUNI stop search endpoints
  listMuniStops: () => fetchApi<{ stops: MuniStop[]; total: number }>("/muni/stops"),
  findNearbyMuniStops: (lat: number, lng: number, radius?: number, limit?: number) => {
    const params = new URLSearchParams({
      lat: lat.toString(),
      lng: lng.toString(),
      ...(radius !== undefined && { radius: radius.toString() }),
      ...(limit !== undefined && { limit: limit.toString() }),
    });
    return fetchApi<{
      stops: MuniStop[];
      count: number;
      search_location: { lat: number; lng: number };
      radius_km: number;
    }>(`/muni/stops/nearby?${params}`);
  },
  searchMuniStopsByAddress: (address: string, radius?: number, limit?: number) => {
    const params = new URLSearchParams({
      address,
      ...(radius !== undefined && { radius: radius.toString() }),
      ...(limit !== undefined && { limit: limit.toString() }),
    });
    return fetchApi<{
      stops: MuniStop[];
      count: number;
      search_address: string;
      geocoded_location: { lat: number; lng: number; display_name: string };
      radius_km: number;
    }>(`/muni/stops/search?${params}`);
  },

  // Traffic route endpoints
  geocodeAddress: (address: string) =>
    fetchApi<{ lat: number; lng: number; formatted_address: string }>("/traffic/routes/geocode", {
      method: "POST",
      body: JSON.stringify({ address }),
    }),
  validateTrafficRoute: (
    origin: string,
    destination: string,
    destination_name: string,
    travel_mode: string = "DRIVE",
  ) =>
    fetchApi<{
      valid: boolean;
      distance_km?: number;
      static_duration_minutes?: number;
      error?: string;
    }>("/traffic/routes/validate", {
      method: "POST",
      body: JSON.stringify({ origin, destination, destination_name, travel_mode }),
    }),

  // Stocks endpoints
  searchStockSymbols: (query: string, limit?: number) => {
    const params = new URLSearchParams({
      query,
      ...(limit !== undefined && { limit: limit.toString() }),
    });
    return fetchApi<{
      symbols: StockSymbol[];
      count: number;
      query: string;
    }>(`/stocks/search?${params}`);
  },
  validateStockSymbol: (symbol: string) =>
    fetchApi<StockSymbolValidation>("/stocks/validate", {
      method: "POST",
      body: JSON.stringify({ symbol }),
    }),
  // Generic Data helper
  genericDataTestFetch: (request: {
    url: string;
    format?: string;
    method?: string;
    headers?: { name: string; value: string }[];
    body?: string;
  }) =>
    fetchApi<{ ok: boolean; data: unknown }>("/generic-data/test-fetch", {
      method: "POST",
      body: JSON.stringify(request),
    }),
};
