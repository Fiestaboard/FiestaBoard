"use client";

import { useState, DragEvent, useDeferredValue, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api";
import { ChevronDown, Bike, TrainFront, Car, Home, TrendingUp, Trophy, Plane } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { FIESTABOARD_COLORS } from "@/lib/board-colors";
import { HomeAssistantEntityPicker } from "./home-assistant-entity-picker";

// Color mapping with contrast info - uses board's official colors
const COLOR_MAP: Record<string, { bg: string; needsDarkText: boolean }> = {
  red: { bg: FIESTABOARD_COLORS.red, needsDarkText: false },
  orange: { bg: FIESTABOARD_COLORS.orange, needsDarkText: false },
  yellow: { bg: FIESTABOARD_COLORS.yellow, needsDarkText: true },
  green: { bg: FIESTABOARD_COLORS.green, needsDarkText: true },
  blue: { bg: FIESTABOARD_COLORS.blue, needsDarkText: false },
  violet: { bg: FIESTABOARD_COLORS.violet, needsDarkText: false },
  white: { bg: FIESTABOARD_COLORS.white, needsDarkText: true },
  black: { bg: FIESTABOARD_COLORS.black, needsDarkText: false },
};

interface VariablePickerProps {
  onInsert?: (variable: string) => void;
  showColors?: boolean;
  showSymbols?: boolean;
}

function CollapsibleSection({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="border-b border-border/50 last:border-b-0">
      <CollapsibleTrigger className="flex items-center justify-between w-full py-2 text-left text-xs font-medium text-muted-foreground hover:text-foreground transition-colors">
        <span className="capitalize">{title.replace(/_/g, " ")}</span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 transition-transform duration-200",
            isOpen && "rotate-180"
          )}
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="overflow-y-auto pb-3">
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}

// Variable pill component - matches editor badge style
function VariablePill({
  label,
  value: _value,
  onInsert,
  onDragStart,
}: {
  label: string;
  value: string;
  onInsert: () => void;
  onDragStart: (e: DragEvent<HTMLButtonElement>) => void;
}) {
  return (
    <Badge
      variant="variable"
      asChild
      className="px-2.5 py-1 cursor-grab active:cursor-grabbing hover:bg-indigo-500/25"
    >
      <button type="button" draggable onDragStart={onDragStart} onClick={onInsert}>
        {label}
      </button>
    </Badge>
  );
}

// Color pill component - solid color like in editor
function ColorPill({
  colorName,
  onInsert,
  onDragStart,
}: {
  colorName: string;
  onInsert: () => void;
  onDragStart: (e: DragEvent<HTMLButtonElement>) => void;
}) {
  const colorInfo = COLOR_MAP[colorName.toLowerCase()];
  if (!colorInfo) return null;

  return (
    <button
      type="button"
      draggable
      onDragStart={onDragStart}
      onClick={onInsert}
      style={{ backgroundColor: colorInfo.bg }}
      className={cn(
        "inline-flex items-center justify-center rounded-full px-3 py-1 text-xs font-medium",
        "cursor-grab active:cursor-grabbing transition-all hover:scale-105",
        colorInfo.needsDarkText ? "text-black/80" : "text-white/90"
      )}
      aria-label={`${colorName} color`}
    >
      {colorName}
    </button>
  );
}

interface BayWheelsStationData {
  station_id: string;
  station_name: string;
  electric_bikes: number;
  classic_bikes: number;
  num_bikes_available: number;
  status_color: string;
  is_renting: boolean;
  num_docks_available: number;
}

export function VariablePicker({
  onInsert,
  showColors = true,
}: VariablePickerProps) {
  const [showEntityPicker, setShowEntityPicker] = useState(false);
  
  const { data: templateVars, isLoading } = useQuery({
    queryKey: ["template-variables"],
    queryFn: api.getTemplateVariables,
  });

  // Determine which plugins are enabled from templateVars
  const enabledPlugins = useMemo(() => {
    if (!templateVars?.variables) return [];
    const pluginKeys = ['baywheels', 'muni', 'traffic', 'weather', 'stocks', 'sports_scores', 'nearby_aircraft'];
    return pluginKeys.filter(key => templateVars.variables[key] !== undefined);
  }, [templateVars]);

  // Single batch query instead of 7+ individual queries
  const { data: pluginDisplayData } = useQuery({
    queryKey: ["plugin-displays-batch", enabledPlugins],
    queryFn: () => api.getDisplaysRawBatch(enabledPlugins),
    refetchInterval: 15000,
    enabled: enabledPlugins.length > 0,
  });

  // Extract individual plugin data from batch response
  const baywheelsData = useMemo(() => 
    pluginDisplayData?.displays?.baywheels?.data as { stations?: BayWheelsStationData[] } | null | undefined
  , [pluginDisplayData]);
  
  const muniData = useMemo(() => 
    pluginDisplayData?.displays?.muni?.data as { stops?: any[] } | null | undefined
  , [pluginDisplayData]);
  
  const trafficData = useMemo(() => 
    pluginDisplayData?.displays?.traffic?.data as { routes?: any[] } | null | undefined
  , [pluginDisplayData]);
  
  const weatherData = useMemo(() => 
    pluginDisplayData?.displays?.weather?.data as { locations?: any[] } | null | undefined
  , [pluginDisplayData]);
  
  const stocksData = useMemo(() => 
    pluginDisplayData?.displays?.stocks?.data as { stocks?: any[] } | null | undefined
  , [pluginDisplayData]);
  
  const sportsScoresData = useMemo(() => 
    pluginDisplayData?.displays?.sports_scores?.data as { games?: any[] } | null | undefined ?? { games: [] }
  , [pluginDisplayData]);
  
  const nearbyAircraftData = useMemo(() => 
    pluginDisplayData?.displays?.nearby_aircraft?.data as { aircraft?: any[] } | null | undefined
  , [pluginDisplayData]);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied to clipboard");
  };

  const handleInsert = (variable: string) => {
    if (onInsert) {
      onInsert(variable);
    } else {
      handleCopy(variable);
    }
  };

  const handleDragStart = (e: DragEvent<HTMLButtonElement>, value: string) => {
    e.dataTransfer.effectAllowed = "copy";
    e.dataTransfer.setData("text/plain", value);
    e.dataTransfer.setData("application/x-template-variable", value);
  };

  // Helper to get status emoji
  const getStatusEmoji = (electricBikes: number) => {
    if (electricBikes < 2) return "🔴";
    if (electricBikes > 5) return "🟢";
    return "🟡";
  };

  // Use deferred values for live data to reduce re-render priority
  const deferredBaywheelsData = useDeferredValue(baywheelsData);
  const deferredMuniData = useDeferredValue(muniData);
  const deferredTrafficData = useDeferredValue(trafficData);
  const deferredWeatherData = useDeferredValue(weatherData);
  const deferredStocksData = useDeferredValue(stocksData);
  const deferredSportsScoresData = useDeferredValue(sportsScoresData);
  const deferredNearbyAircraftData = useDeferredValue(nearbyAircraftData);

  return (
    <>
      <Card className="flex flex-col h-full min-h-0">
      <CardHeader className="flex-shrink-0 px-4 sm:px-6 pb-2">
        <CardTitle className="text-base">Template Variables</CardTitle>
        <CardDescription className="text-xs sm:text-sm">
          {isLoading ? (
            <Skeleton className="h-4 w-48" />
          ) : (
            <>Tap to {onInsert ? "insert" : "copy"} or drag into template</>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 flex flex-col overflow-y-auto px-4 sm:px-6 pt-0">
        {isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : !templateVars ? null : (
        <div className="space-y-1">
          {/* Data Variables - collapsible by category */}
          <div className="pb-2">
            <h4 className="text-sm font-semibold mb-2">Data Variables</h4>
            {Object.entries(templateVars.variables).map(([category, vars]) => {
              // Special handling for BayWheels with live station data
              if (category === "baywheels" && deferredBaywheelsData?.stations && deferredBaywheelsData.stations.length > 0) {
                return (
                  <CollapsibleSection key={category} title={category} defaultOpen={false}>
                    <div className="space-y-3">
                      {/* Aggregate/General Variables */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-1.5">General</p>
                        <div className="flex flex-wrap gap-1.5">
                          {vars.filter(v => !v.startsWith("stations.")).map((variable) => {
                            const varValue = `{{${category}.${variable}}}`;
                            return (
                              <VariablePill
                                key={variable}
                                label={variable}
                                value={varValue}
                                onInsert={() => handleInsert(varValue)}
                                onDragStart={(e) => handleDragStart(e, varValue)}
                              />
                            );
                          })}
                        </div>
                      </div>

                      {/* Individual Stations Accordion */}
                      <div className="space-y-1.5">
                        <p className="text-xs text-muted-foreground flex items-center gap-1">
                          <Bike className="h-3 w-3" />
                          Stations ({deferredBaywheelsData.stations.length})
                        </p>
                        <ScrollArea className="max-h-[400px] pr-1">
                          <Accordion type="single" collapsible className="w-full">
                            {deferredBaywheelsData.stations.map((station, index) => (
                            <AccordionItem key={station.station_id} value={`station-${index}`} className="border-b-0">
                              <AccordionTrigger className="py-2 hover:no-underline">
                                <div className="flex items-center gap-2 text-xs">
                                  <span className="text-lg">{getStatusEmoji(station.electric_bikes)}</span>
                                  <div className="text-left">
                                    <div className="font-medium">{station.station_name}</div>
                                    <div className="text-muted-foreground text-xs">
                                      {station.electric_bikes}⚡ {station.classic_bikes}🚲 • Index: {index}
                                    </div>
                                  </div>
                                </div>
                              </AccordionTrigger>
                              <AccordionContent>
                                <div className="space-y-2 pt-2 pl-2">
                                  <div className="flex flex-wrap gap-1.5">
                                    {["electric_bikes", "classic_bikes", "num_bikes_available", "status_color", "is_renting", "station_name"].map((field) => {
                                      const varValue = `{{${category}.stations.${index}.${field}}}`;
                                      return (
                                        <VariablePill
                                          key={field}
                                          label={field}
                                          value={varValue}
                                          onInsert={() => handleInsert(varValue)}
                                          onDragStart={(e) => handleDragStart(e, varValue)}
                                        />
                                      );
                                    })}
                                  </div>
                                  <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                                    <code className="text-xs">stations.{index}.*</code>
                                  </div>
                                </div>
                              </AccordionContent>
                            </AccordionItem>
                          ))}
                          </Accordion>
                        </ScrollArea>
                      </div>
                    </div>
                  </CollapsibleSection>
                );
              }

              // Special handling for Home Assistant - opens entity picker modal
              if (category === "home_assistant") {
                return (
                  <CollapsibleSection key={category} title="Home Assistant" defaultOpen={false}>
                    <div className="space-y-2">
                      <button
                        onClick={() => setShowEntityPicker(true)}
                        className="w-full text-left p-3 rounded-md border border-dashed border-primary/50 hover:border-primary hover:bg-primary/5 transition-all"
                      >
                        <div className="flex items-center gap-2">
                          <Home className="h-4 w-4 text-primary" />
                          <div>
                            <div className="font-medium text-sm">Select Entity</div>
                            <div className="text-xs text-muted-foreground">
                              Click to choose an entity and attribute
                            </div>
                          </div>
                        </div>
                      </button>
                      <div className="text-xs text-muted-foreground bg-muted/30 p-2 rounded">
                        <p>Opens a modal to browse all Home Assistant entities</p>
                      </div>
                    </div>
                  </CollapsibleSection>
                );
              }

              // Special handling for MUNI with live stop data OR when enabled but no stops yet
              if (category === "muni") {
                return (
                  <CollapsibleSection key={category} title={category} defaultOpen={false}>
                    <div className="space-y-3">
                      {/* Aggregate/General Variables */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-1.5">General</p>
                        <div className="flex flex-wrap gap-1.5">
                          {vars.filter(v => !v.startsWith("stops.")).map((variable) => {
                            const varValue = `{{${category}.${variable}}}`;
                            return (
                              <VariablePill
                                key={variable}
                                label={variable}
                                value={varValue}
                                onInsert={() => handleInsert(varValue)}
                                onDragStart={(e) => handleDragStart(e, varValue)}
                              />
                            );
                          })}
                        </div>
                      </div>

                      {/* Individual Stops Accordion */}
                      <div className="space-y-1.5">
                        <p className="text-xs text-muted-foreground flex items-center gap-1">
                          <TrainFront className="h-3 w-3" />
                          Stops {deferredMuniData?.stops ? `(${deferredMuniData.stops.length})` : "(None configured)"}
                        </p>
                        {deferredMuniData?.stops && deferredMuniData.stops.length > 0 ? (
                          <ScrollArea className="max-h-[400px] pr-1">
                            <Accordion type="single" collapsible className="w-full">
                              {deferredMuniData.stops.map((stop: any, index: number) => (
                              <AccordionItem key={stop.stop_code || index} value={`stop-${index}`} className="border-b-0">
                                <AccordionTrigger className="py-2 hover:no-underline">
                                  <div className="flex items-center gap-2 text-xs">
                                    <TrainFront className="h-4 w-4" />
                                    <div className="text-left">
                                      <div className="font-medium">{stop.stop_name || stop.stop_code}</div>
                                      <div className="text-muted-foreground text-xs">
                                        {stop.line} • Index: {index}
                                      </div>
                                    </div>
                                  </div>
                                </AccordionTrigger>
                                <AccordionContent>
                                  <div className="space-y-3 pt-2 pl-2">
                                    {/* Stop-level variables */}
                                    <div>
                                      <p className="text-xs text-muted-foreground mb-1.5">Stop Info</p>
                                      <div className="flex flex-wrap gap-1.5">
                                        {["stop_name", "stop_code"].map((field) => {
                                          const varValue = `{{${category}.stops.${index}.${field}}}`;
                                          return (
                                            <VariablePill
                                              key={field}
                                              label={field}
                                              value={varValue}
                                              onInsert={() => handleInsert(varValue)}
                                              onDragStart={(e) => handleDragStart(e, varValue)}
                                            />
                                          );
                                        })}
                                      </div>
                                    </div>

                                    {/* All Lines combined */}
                                    <div>
                                      <p className="text-xs text-muted-foreground mb-1.5">All Lines (Combined)</p>
                                      <div className="flex flex-wrap gap-1.5">
                                        {["all_lines.formatted", "all_lines.next_arrival"].map((field) => {
                                          const varValue = `{{${category}.stops.${index}.${field}}}`;
                                          return (
                                            <VariablePill
                                              key={field}
                                              label={field.split('.')[1]}
                                              value={varValue}
                                              onInsert={() => handleInsert(varValue)}
                                              onDragStart={(e) => handleDragStart(e, varValue)}
                                            />
                                          );
                                        })}
                                      </div>
                                    </div>

                                    {/* Lines nested accordion */}
                                    {stop.lines && Object.keys(stop.lines).length > 0 && (
                                      <div>
                                        <p className="text-xs text-muted-foreground mb-1.5 flex items-center gap-1">
                                          <TrainFront className="h-3 w-3" />
                                          Lines ({Object.keys(stop.lines).length})
                                        </p>
                                        <Accordion type="single" collapsible className="w-full">
                                          {Object.entries(stop.lines).map(([lineCode, lineData]: [string, any]) => (
                                            <AccordionItem key={lineCode} value={`stop-${index}-line-${lineCode}`} className="border-b-0">
                                              <AccordionTrigger className="py-1.5 hover:no-underline text-xs">
                                                <div className="flex items-center gap-2">
                                                  <Badge variant="outline" className="text-[10px] font-mono px-1.5">
                                                    {lineCode}
                                                  </Badge>
                                                  <span className="text-left">{lineData.line || lineCode}</span>
                                                  {lineData.next_arrival && (
                                                    <span className="text-muted-foreground text-[10px]">
                                                      {lineData.next_arrival}m
                                                    </span>
                                                  )}
                                                </div>
                                              </AccordionTrigger>
                                              <AccordionContent>
                                                <div className="space-y-2 pt-2 pl-2">
                                                  <div className="flex flex-wrap gap-1.5">
                                                    {["formatted", "next_arrival", "is_delayed", "line"].map((field) => {
                                                      const varValue = `{{${category}.stops.${index}.lines.${lineCode}.${field}}}`;
                                                      return (
                                                        <VariablePill
                                                          key={field}
                                                          label={field}
                                                          value={varValue}
                                                          onInsert={() => handleInsert(varValue)}
                                                          onDragStart={(e) => handleDragStart(e, varValue)}
                                                        />
                                                      );
                                                    })}
                                                  </div>
                                                  <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                                                    <code className="text-xs">stops.{index}.lines.{lineCode}.*</code>
                                                  </div>
                                                </div>
                                              </AccordionContent>
                                            </AccordionItem>
                                          ))}
                                        </Accordion>
                                      </div>
                                    )}
                                  </div>
                                </AccordionContent>
                              </AccordionItem>
                            ))}
                            </Accordion>
                          </ScrollArea>
                        ) : (
                          <div className="p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground">
                            <p className="mb-2">Configure stops in Settings to see indexed variables here.</p>
                            <p className="font-mono text-[10px]">
                              Example: <code className="bg-background px-1 rounded">stops.0.line</code>, <code className="bg-background px-1 rounded">stops.1.formatted</code>
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </CollapsibleSection>
                );
              }

              // Special handling for Traffic with live route data OR when enabled but no routes yet
              if (category === "traffic") {
                return (
                  <CollapsibleSection key={category} title={category} defaultOpen={false}>
                    <div className="space-y-3">
                      {/* Aggregate/General Variables */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-1.5">General</p>
                        <div className="flex flex-wrap gap-1.5">
                          {vars.filter(v => !v.startsWith("routes.")).map((variable) => {
                            const varValue = `{{${category}.${variable}}}`;
                            return (
                              <VariablePill
                                key={variable}
                                label={variable}
                                value={varValue}
                                onInsert={() => handleInsert(varValue)}
                                onDragStart={(e) => handleDragStart(e, varValue)}
                              />
                            );
                          })}
                        </div>
                      </div>

                      {/* Individual Routes Accordion */}
                      <div className="space-y-1.5">
                        <p className="text-xs text-muted-foreground flex items-center gap-1">
                          <Car className="h-3 w-3" />
                          Routes {deferredTrafficData?.routes ? `(${deferredTrafficData.routes.length})` : "(None configured)"}
                        </p>
                        {deferredTrafficData?.routes && deferredTrafficData.routes.length > 0 ? (
                          <ScrollArea className="max-h-[400px] pr-1">
                            <Accordion type="single" collapsible className="w-full">
                              {deferredTrafficData.routes.map((route: any, index: number) => (
                              <AccordionItem key={index} value={`route-${index}`} className="border-b-0">
                                <AccordionTrigger className="py-2 hover:no-underline">
                                  <div className="flex items-center gap-2 text-xs">
                                    <Car className="h-4 w-4" />
                                    <div className="text-left">
                                      <div className="font-medium">{route.destination_name}</div>
                                      <div className="text-muted-foreground text-xs">
                                        {route.duration_minutes}m • {route.traffic_status} • Index: {index}
                                      </div>
                                    </div>
                                  </div>
                                </AccordionTrigger>
                                <AccordionContent>
                                  <div className="space-y-2 pt-2 pl-2">
                                    <div className="flex flex-wrap gap-1.5">
                                      {["duration_minutes", "delay_minutes", "traffic_status", "destination_name", "formatted"].map((field) => {
                                        const varValue = `{{${category}.routes.${index}.${field}}}`;
                                        return (
                                          <VariablePill
                                            key={field}
                                            label={field}
                                            value={varValue}
                                            onInsert={() => handleInsert(varValue)}
                                            onDragStart={(e) => handleDragStart(e, varValue)}
                                          />
                                        );
                                      })}
                                    </div>
                                    <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                                      <code className="text-xs">routes.{index}.*</code>
                                    </div>
                                  </div>
                                </AccordionContent>
                              </AccordionItem>
                            ))}
                            </Accordion>
                          </ScrollArea>
                        ) : (
                          <div className="p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground">
                            <p className="mb-2">Configure routes in Settings to see indexed variables here.</p>
                            <p className="font-mono text-[10px]">
                              Example: <code className="bg-background px-1 rounded">routes.0.duration_minutes</code>, <code className="bg-background px-1 rounded">routes.1.formatted</code>
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </CollapsibleSection>
                );
              }

              // Special handling for Weather with live location data
              if (category === "weather") {
                return (
                  <CollapsibleSection key={category} title={category} defaultOpen={false}>
                    <div className="space-y-3">
                      {/* General Variables */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-1.5">General</p>
                        <div className="flex flex-wrap gap-1.5">
                          {vars.filter(v => !v.startsWith("locations.")).map((variable) => {
                            const varValue = `{{${category}.${variable}}}`;
                            return (
                              <VariablePill
                                key={variable}
                                label={variable}
                                value={varValue}
                                onInsert={() => handleInsert(varValue)}
                                onDragStart={(e) => handleDragStart(e, varValue)}
                              />
                            );
                          })}
                        </div>
                      </div>

                      {/* Individual Locations */}
                      <div className="space-y-1.5">
                        <p className="text-xs text-muted-foreground">
                          Locations {deferredWeatherData?.locations ? `(${deferredWeatherData.locations.length})` : "(1)"}
                        </p>
                        {deferredWeatherData?.locations && deferredWeatherData.locations.length > 0 ? (
                          <div className="space-y-2">
                            {deferredWeatherData.locations.map((location: any, index: number) => (
                              <div key={index} className="p-2 bg-muted/30 rounded-lg">
                                <p className="text-xs font-medium mb-1.5">
                                  {location.location_name || `Location ${index}`} - {location.location || "Unknown"}
                                </p>
                                <div className="flex flex-wrap gap-1.5">
                                  {["temperature", "condition", "humidity", "wind_speed", "location_name", "feels_like"].map((field) => {
                                    const varValue = `{{${category}.locations.${index}.${field}}}`;
                                    return (
                                      <VariablePill
                                        key={field}
                                        label={field}
                                        value={varValue}
                                        onInsert={() => handleInsert(varValue)}
                                        onDragStart={(e) => handleDragStart(e, varValue)}
                                      />
                                    );
                                  })}
                                </div>
                                <div className="text-xs text-muted-foreground mt-1.5 font-mono">
                                  <code className="text-[10px]">locations.{index}.*</code>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground">
                            <p className="mb-2">Configure locations in Settings to see indexed variables here.</p>
                            <p className="font-mono text-[10px]">
                              Example: <code className="bg-background px-1 rounded">locations.0.temperature</code>, <code className="bg-background px-1 rounded">locations.1.condition</code>
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </CollapsibleSection>
                );
              }

              // Special handling for Stocks with live stock data OR when enabled but no stocks yet
              if (category === "stocks") {
                return (
                  <CollapsibleSection key={category} title={category} defaultOpen={false}>
                    <div className="space-y-3">
                      {/* Aggregate/General Variables */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-1.5">General</p>
                        <div className="flex flex-wrap gap-1.5">
                          {vars.filter(v => !v.startsWith("stocks.")).map((variable) => {
                            const varValue = `{{${category}.${variable}}}`;
                            return (
                              <VariablePill
                                key={variable}
                                label={variable}
                                value={varValue}
                                onInsert={() => handleInsert(varValue)}
                                onDragStart={(e) => handleDragStart(e, varValue)}
                              />
                            );
                          })}
                        </div>
                      </div>

                      {/* Individual Stocks Accordion */}
                      <div className="space-y-1.5">
                        <p className="text-xs text-muted-foreground flex items-center gap-1">
                          <TrendingUp className="h-3 w-3" />
                          Stocks {deferredStocksData?.stocks ? `(${deferredStocksData.stocks.length})` : "(None configured)"}
                        </p>
                        {deferredStocksData?.stocks && deferredStocksData.stocks.length > 0 ? (
                          <ScrollArea className="max-h-[400px] pr-1">
                            <Accordion type="single" collapsible className="w-full">
                              {deferredStocksData.stocks.map((stock: any, index: number) => (
                              <AccordionItem key={stock.symbol || index} value={`stock-${index}`} className="border-b-0">
                                <AccordionTrigger className="py-2 hover:no-underline">
                                  <div className="flex items-center gap-2 text-xs">
                                    <TrendingUp className="h-4 w-4" />
                                    <div className="text-left">
                                      <div className="font-medium">{stock.symbol || `Stock ${index}`}</div>
                                      <div className="text-muted-foreground text-xs">
                                        ${stock.current_price?.toFixed(2) || "N/A"} • {stock.change_percent ? `${stock.change_percent >= 0 ? '+' : ''}${stock.change_percent.toFixed(2)}%` : "N/A"} • Index: {index}
                                      </div>
                                    </div>
                                  </div>
                                </AccordionTrigger>
                                <AccordionContent>
                                  <div className="space-y-2 pt-2 pl-2">
                                    <div className="flex flex-wrap gap-1.5">
                                      {["symbol", "current_price", "previous_price", "change_percent", "change_direction", "formatted", "company_name"].map((field) => {
                                        const varValue = `{{${category}.stocks.${index}.${field}}}`;
                                        return (
                                          <VariablePill
                                            key={field}
                                            label={field}
                                            value={varValue}
                                            onInsert={() => handleInsert(varValue)}
                                            onDragStart={(e) => handleDragStart(e, varValue)}
                                          />
                                        );
                                      })}
                                    </div>
                                    <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                                      <code className="text-xs">stocks.{index}.*</code>
                                    </div>
                                  </div>
                                </AccordionContent>
                              </AccordionItem>
                            ))}
                            </Accordion>
                          </ScrollArea>
                        ) : (
                          <div className="p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground">
                            <p className="mb-2">Configure stock symbols in Settings to see indexed variables here.</p>
                            <p className="font-mono text-[10px]">
                              Example: <code className="bg-background px-1 rounded">stocks.0.symbol</code>, <code className="bg-background px-1 rounded">stocks.1.current_price</code>, <code className="bg-background px-1 rounded">stocks.2.formatted</code>
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </CollapsibleSection>
                );
              }

              // Special handling for Sports Scores with live game data OR when enabled but no games yet
              if (category === "sports_scores") {
                return (
                  <CollapsibleSection key={category} title={category} defaultOpen={false}>
                    <div className="space-y-3">
                      {/* Aggregate/General Variables */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-1.5">General</p>
                        <div className="flex flex-wrap gap-1.5">
                          {vars.filter(v => !v.startsWith("games.")).map((variable) => {
                            const varValue = `{{${category}.${variable}}}`;
                            return (
                              <VariablePill
                                key={variable}
                                label={variable}
                                value={varValue}
                                onInsert={() => handleInsert(varValue)}
                                onDragStart={(e) => handleDragStart(e, varValue)}
                              />
                            );
                          })}
                        </div>
                      </div>

                      {/* Individual Games Accordion */}
                      <div className="space-y-1.5">
                        <p className="text-xs text-muted-foreground flex items-center gap-1">
                          <Trophy className="h-3 w-3" />
                          Games {deferredSportsScoresData?.games !== undefined ? `(${deferredSportsScoresData.games.length})` : "(None configured)"}
                        </p>
                        {deferredSportsScoresData?.games && deferredSportsScoresData.games.length > 0 ? (
                          <ScrollArea className="max-h-[400px] pr-1">
                            <Accordion type="single" collapsible className="w-full">
                              {deferredSportsScoresData.games.map((game: any, index: number) => (
                              <AccordionItem key={game.formatted || index} value={`game-${index}`} className="border-b-0">
                                <AccordionTrigger className="py-2 hover:no-underline">
                                  <div className="flex items-center gap-2 text-xs">
                                    <Trophy className="h-4 w-4" />
                                    <div className="text-left">
                                      <div className="font-medium">{game.team1 || `Team 1`} vs {game.team2 || `Team 2`}</div>
                                      <div className="text-muted-foreground text-xs">
                                        {game.score1 !== undefined && game.score2 !== undefined ? `${game.score1} - ${game.score2}` : game.status || "Scheduled"} • {game.sport || "N/A"} • Index: {index}
                                      </div>
                                    </div>
                                  </div>
                                </AccordionTrigger>
                                <AccordionContent>
                                  <div className="space-y-2 pt-2 pl-2">
                                    <div className="flex flex-wrap gap-1.5">
                                      {["sport", "team1", "team2", "team1_full", "team2_full", "team1_color", "team2_color", "score1", "score2", "status", "date", "time", "formatted"].map((field) => {
                                        const varValue = `{{${category}.games.${index}.${field}}}`;
                                        return (
                                          <VariablePill
                                            key={field}
                                            label={field}
                                            value={varValue}
                                            onInsert={() => handleInsert(varValue)}
                                            onDragStart={(e) => handleDragStart(e, varValue)}
                                          />
                                        );
                                      })}
                                    </div>
                                    <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                                      <code className="text-xs">games.{index}.*</code>
                                    </div>
                                  </div>
                                </AccordionContent>
                              </AccordionItem>
                            ))}
                            </Accordion>
                          </ScrollArea>
                        ) : (
                          <div className="p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground">
                            <p className="mb-2">Configure sports in Settings to see indexed variables here.</p>
                            <p className="font-mono text-[10px]">
                              Example: <code className="bg-background px-1 rounded">games.0.team1</code>, <code className="bg-background px-1 rounded">games.1.score1</code>, <code className="bg-background px-1 rounded">games.2.formatted</code>
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </CollapsibleSection>
                );
              }

              // Special handling for Nearby Aircraft with live aircraft data
              if (category === "nearby_aircraft") {
                return (
                  <CollapsibleSection key={category} title={category} defaultOpen={false}>
                    <div className="space-y-3">
                      {/* Aggregate/General Variables */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-1.5">General</p>
                        <div className="flex flex-wrap gap-1.5">
                          {vars.filter((v: string) => !v.startsWith("aircraft.")).map((variable: string) => {
                            const varValue = `{{${category}.${variable}}}`;
                            return (
                              <VariablePill
                                key={variable}
                                label={variable}
                                value={varValue}
                                onInsert={() => handleInsert(varValue)}
                                onDragStart={(e) => handleDragStart(e, varValue)}
                              />
                            );
                          })}
                        </div>
                      </div>

                      {/* Individual Aircraft Accordion */}
                      <div className="space-y-1.5">
                        <p className="text-xs text-muted-foreground flex items-center gap-1">
                          <Plane className="h-3 w-3" />
                          Aircraft {deferredNearbyAircraftData?.aircraft ? `(${deferredNearbyAircraftData.aircraft.length})` : "(None detected)"}
                        </p>
                        {deferredNearbyAircraftData?.aircraft && deferredNearbyAircraftData.aircraft.length > 0 ? (
                          <ScrollArea className="max-h-[400px] pr-1">
                            <Accordion type="single" collapsible className="w-full">
                              {deferredNearbyAircraftData.aircraft.map((aircraft: any, index: number) => (
                              <AccordionItem key={aircraft.call_sign || aircraft.icao24 || index} value={`aircraft-${index}`} className="border-b-0">
                                <AccordionTrigger className="py-2 hover:no-underline">
                                  <div className="flex items-center gap-2 text-xs">
                                    <Plane className="h-4 w-4" />
                                    <div className="text-left">
                                      <div className="font-medium">{aircraft.call_sign || aircraft.icao24 || `Aircraft ${index}`}</div>
                                      <div className="text-muted-foreground text-xs">
                                        {aircraft.altitude?.toLocaleString() || "N/A"}ft • {aircraft.ground_speed || "N/A"}kt • {aircraft.distance_km?.toFixed(1) || "N/A"}km away • Index: {index}
                                      </div>
                                    </div>
                                  </div>
                                </AccordionTrigger>
                                <AccordionContent>
                                  <div className="space-y-2 pt-2 pl-2">
                                    <div className="flex flex-wrap gap-1.5">
                                      {["icao24", "call_sign", "altitude", "ground_speed", "squawk", "latitude", "longitude", "distance_km", "formatted"].map((field) => {
                                        const varValue = `{{${category}.aircraft.${index}.${field}}}`;
                                        return (
                                          <VariablePill
                                            key={field}
                                            label={field}
                                            value={varValue}
                                            onInsert={() => handleInsert(varValue)}
                                            onDragStart={(e) => handleDragStart(e, varValue)}
                                          />
                                        );
                                      })}
                                    </div>
                                    <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                                      <code className="text-xs">aircraft.{index}.*</code>
                                    </div>
                                  </div>
                                </AccordionContent>
                              </AccordionItem>
                            ))}
                            </Accordion>
                          </ScrollArea>
                        ) : (
                          <div className="p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground">
                            <p className="mb-2">Enable Nearby Aircraft in Settings and configure your location to see aircraft here.</p>
                            <p className="font-mono text-[10px]">
                              Example: <code className="bg-background px-1 rounded">aircraft.0.call_sign</code>, <code className="bg-background px-1 rounded">aircraft.1.altitude</code>, <code className="bg-background px-1 rounded">aircraft.2.formatted</code>
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </CollapsibleSection>
                );
              }

              // Default handling for other categories
              return (
                <CollapsibleSection key={category} title={category} defaultOpen={false}>
                  <div className="flex flex-wrap gap-1.5">
                    {vars.map((variable) => {
                      const varValue = `{{${category}.${variable}}}`;
                      return (
                        <VariablePill
                          key={variable}
                          label={variable}
                          value={varValue}
                          onInsert={() => handleInsert(varValue)}
                          onDragStart={(e) => handleDragStart(e, varValue)}
                        />
                      );
                    })}
                  </div>
                </CollapsibleSection>
              );
            })}
          </div>

          {/* Colors */}
          {showColors && Object.keys(templateVars.colors).length > 0 && (
            <div className="py-2 border-t border-border/50">
              <h4 className="text-sm font-semibold mb-3">Colors</h4>
              <div className="flex flex-wrap gap-2">
                {Object.entries(templateVars.colors).map(([colorName]) => {
                  const colorValue = `{${colorName}}`;
                  return (
                    <ColorPill
                      key={colorName}
                      colorName={colorName}
                      onInsert={() => handleInsert(colorValue)}
                      onDragStart={(e) => handleDragStart(e, colorValue)}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* Formatting */}
          {templateVars.formatting && Object.keys(templateVars.formatting).length > 0 && (
            <div className="py-2 border-t border-border/50">
              <h4 className="text-sm font-semibold mb-3">Formatting</h4>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(templateVars.formatting).map(([name, info]) => (
                  <VariablePill
                    key={name}
                    label={name.replace(/_/g, " ")}
                    value={info.syntax}
                    onInsert={() => handleInsert(info.syntax)}
                    onDragStart={(e) => handleDragStart(e, info.syntax)}
                  />
                ))}
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                Use fill_space to push content apart: {"Left{{fill_space}}Right"}
              </p>
            </div>
          )}

          {/* Filters */}
          {templateVars.filters.length > 0 && (
            <div className="py-2 border-t border-border/50">
              <h4 className="text-sm font-semibold mb-3">Filters</h4>
              <div className="flex flex-wrap gap-1.5">
                {templateVars.filters.map((filter) => (
                  <Badge
                    key={filter}
                    variant="secondary"
                    className="cursor-pointer text-xs py-1 px-2 font-mono active:bg-muted"
                    onClick={() => handleCopy(`|${filter}`)}
                  >
                    |{filter}
                  </Badge>
                ))}
              </div>
              <div className="text-xs text-muted-foreground mt-2 space-y-1">
                <p>Example: {"{{weather.temperature|pad:3}}"}</p>
                <p><strong>|wrap</strong>: Wraps long text across multiple lines. Leave consecutive empty lines below for text to flow into.</p>
              </div>
            </div>
          )}
        </div>
        )}
      </CardContent>
    </Card>
      
      <HomeAssistantEntityPicker
        open={showEntityPicker}
        onClose={() => setShowEntityPicker(false)}
        onSelect={(variable) => {
          handleInsert(variable);
          setShowEntityPicker(false);
        }}
      />
    </>
  );
}
