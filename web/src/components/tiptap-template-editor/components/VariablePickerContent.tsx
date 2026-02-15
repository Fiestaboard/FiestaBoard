/**
 * Variable Picker Content - Extensible variable list for toolbar dropdown
 * Automatically detects and renders nested arrays from plugin manifests
 */
"use client";

import { useQuery, useQueries } from "@tanstack/react-query";
import { useMemo, useDeferredValue, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api, PluginManifest } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Code2, Home, Bike, TrainFront, Car, TrendingUp, Trophy, Plane, Cloud, Search } from "lucide-react";

interface VariablePickerContentProps {
  onInsert: (variable: string) => void;
}

// Icon mapping for categories
const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  baywheels: <Bike className="h-3 w-3" />,
  muni: <TrainFront className="h-3 w-3" />,
  traffic: <Car className="h-3 w-3" />,
  weather: <Cloud className="h-3 w-3" />,
  stocks: <TrendingUp className="h-3 w-3" />,
  sports_scores: <Trophy className="h-3 w-3" />,
  nearby_aircraft: <Plane className="h-3 w-3" />,
  home_assistant: <Home className="h-3 w-3" />,
  datetime: null,
};

function VariablePill({
  label,
  onInsert,
}: {
  label: string;
  value: string;
  onInsert: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onInsert}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-mono",
        "bg-indigo-500/15 border border-indigo-500/30 text-indigo-700 dark:text-indigo-300",
        "hover:bg-indigo-500/25 transition-colors cursor-pointer"
      )}
    >
      {label}
    </button>
  );
}

// Check if a plugin has nested arrays in its manifest
function hasNestedArrays(manifest: PluginManifest | undefined): boolean {
  if (!manifest?.variables?.arrays) return false;
  return Object.keys(manifest.variables.arrays).length > 0;
}

// Get the array name from a plugin (e.g., "stops", "stations", "routes")
function getArrayName(manifest: PluginManifest | undefined): string | null {
  if (!manifest?.variables?.arrays) return null;
  const arrayKeys = Object.keys(manifest.variables.arrays);
  return arrayKeys.length > 0 ? arrayKeys[0] : null;
}

// Helper function to check if a string matches search query (case-insensitive, more permissive)
function matchesSearch(text: string, searchQuery: string): boolean {
  if (!searchQuery.trim()) return true;
  const normalizedText = text.toLowerCase();
  const normalizedQuery = searchQuery.toLowerCase();
  return normalizedText.includes(normalizedQuery);
}

// Helper function to check if a variable path matches search query (matches category, variable name, or any part)
function matchesVariablePath(category: string, variable: string, searchQuery: string): boolean {
  if (!searchQuery.trim()) return true;
  const normalizedQuery = searchQuery.toLowerCase();
  const categoryLower = category.toLowerCase();
  const variableLower = variable.toLowerCase();
  const fullPath = `${category}.${variable}`.toLowerCase();
  
  // Match if query appears in category, variable, or full path
  return (
    categoryLower.includes(normalizedQuery) ||
    variableLower.includes(normalizedQuery) ||
    fullPath.includes(normalizedQuery) ||
    // Also match individual words in the path
    categoryLower.split(/[._-]/).some(word => word.includes(normalizedQuery)) ||
    variableLower.split(/[._-]/).some(word => word.includes(normalizedQuery))
  );
}

// Render sub-array section (e.g., lines within stops)
function renderSubArraySection(
  pluginId: string,
  parentIndex: number,
  parentArrayName: string,
  subArrayName: string,
  subArrayData: Record<string, any> | undefined,
  manifest: PluginManifest,
  onInsert: (variable: string) => void,
  searchQuery: string,
  showAll: boolean = false,
  icon?: React.ReactNode
) {
  if (!subArrayData || Object.keys(subArrayData).length === 0) return null;

  const subArraySchema = manifest.variables.arrays?.[parentArrayName]?.sub_arrays?.[subArrayName];
  if (!subArraySchema) return null;

  const itemFields = subArraySchema.item_fields || [];
  const keyType = subArraySchema.key_type || "index";
  const keyField = subArraySchema.key_field;
  const labelField = subArraySchema.label_field;

  // Prefer label_field for display (user-friendly name), never raw IDs
  const getItemLabel = (itemData: any) =>
    (labelField && itemData[labelField]) || itemData[keyField] || itemData[itemFields[0]];

  // Filter entries based on search query (if showAll, show all entries)
  const filteredEntries = showAll 
    ? Object.entries(subArrayData)
    : Object.entries(subArrayData).filter(([key, itemData]: [string, any]) => {
        if (!searchQuery.trim()) return true;
    const displayKey = keyType === "dynamic" && keyField ? (itemData[keyField] || key) : key;
    const displayValue = getItemLabel(itemData) ?? displayKey;
    // Check if search matches subArrayName, key, display value, or any field name
    return (
      matchesSearch(subArrayName, searchQuery) ||
      matchesSearch(displayKey, searchQuery) ||
      matchesSearch(String(displayValue), searchQuery) ||
      itemFields.some(field => matchesSearch(field, searchQuery))
    );
  });

  if (filteredEntries.length === 0) return null;

  return (
    <div>
      <p className="text-xs text-muted-foreground mb-1.5 flex items-center gap-1">
        {icon}
        {subArrayName.charAt(0).toUpperCase() + subArrayName.slice(1)} ({filteredEntries.length})
      </p>
      <Accordion type="single" collapsible className="w-full">
        {filteredEntries.map(([key, itemData]: [string, any]) => {
          const displayKey = keyType === "dynamic" && keyField ? (itemData[keyField] || key) : key;
          const itemLabel = getItemLabel(itemData) ?? displayKey;
          const filteredFields = showAll
            ? itemFields
            : itemFields.filter(field => 
                !searchQuery.trim() || matchesSearch(field, searchQuery)
              );
          
          if (filteredFields.length === 0) return null;

          return (
            <AccordionItem key={key} value={`${parentArrayName}-${parentIndex}-${subArrayName}-${key}`} className="border-b-0">
              <AccordionTrigger className="py-1.5 hover:no-underline text-xs">
                <div className="flex items-center gap-2">
                  {keyType === "dynamic" && (
                    <Badge variant="outline" className="text-[10px] font-mono px-1.5">
                      {displayKey}
                    </Badge>
                  )}
                  <span className="text-left">
                    {itemLabel}
                  </span>
                  {itemData.next_arrival && (
                    <span className="text-muted-foreground text-[10px]">
                      {itemData.next_arrival}m
                    </span>
                  )}
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-2 pt-2 pl-2">
                  <div className="flex flex-wrap gap-1.5">
                    {filteredFields.map((field) => {
                      const varValue = `{{${pluginId}.${parentArrayName}.${parentIndex}.${subArrayName}.${key}.${field}}}`;
                      return (
                        <VariablePill
                          key={field}
                          label={field}
                          value={varValue}
                          onInsert={() => onInsert(varValue)}
                        />
                      );
                    })}
                  </div>
                  <div className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                    <code className="text-xs">{parentArrayName}.{parentIndex}.{subArrayName}.{key}.*</code>
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </div>
  );
}

// Render array section (e.g., stops, stations, routes)
function renderArraySection(
  pluginId: string,
  arrayName: string,
  arrayData: any[] | undefined,
  manifest: PluginManifest,
  onInsert: (variable: string) => void,
  searchQuery: string,
  showAll: boolean = false,
  icon?: React.ReactNode
) {
  if (!arrayData || arrayData.length === 0) {
    return (
      <div className="p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground">
        <p className="mb-2">Configure {arrayName} in Settings to see indexed variables here.</p>
        <p className="font-mono text-[10px]">
          Example: <code className="bg-background px-1 rounded">{arrayName}.0.*</code>
        </p>
      </div>
    );
  }

  const arraySchema = manifest.variables.arrays?.[arrayName];
  if (!arraySchema) return null;

  const labelField = arraySchema.label_field || "name";
  const itemFields = arraySchema.item_fields || [];
  const subArrays = arraySchema.sub_arrays || {};

  // Filter array items based on search query, preserving original index
  // If showAll is true (category matched), show all items
  const filteredArrayData = showAll ? arrayData.map((item: any, index: number) => ({ item, index })) :
    arrayData
      .map((item: any, index: number) => ({ item, index }))
      .filter(({ item, index }) => {
        if (!searchQuery.trim()) return true;
      const itemLabel = item[labelField] || item.name || `Item ${index}`;
      const secondaryLabel = item.line || item.destination_name || item.station_name || "";
      // Check if search matches array name, item label, secondary label, or any field name
      return (
        matchesSearch(arrayName, searchQuery) ||
        matchesSearch(itemLabel, searchQuery) ||
        matchesSearch(secondaryLabel, searchQuery) ||
        itemFields.some(field => matchesSearch(field, searchQuery)) ||
        Object.keys(subArrays).some(subArrayName => {
          const subArrayData = item[subArrayName];
          if (!subArrayData) return false;
          return matchesSearch(subArrayName, searchQuery) || 
                 Object.keys(subArrayData).some(key => matchesSearch(key, searchQuery));
        })
      );
    });

  if (filteredArrayData.length === 0) {
    return (
      <div className="p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground">
        <p>No matching variables found.</p>
      </div>
    );
  }

  return (
    <div className="max-h-[400px] overflow-y-auto pr-1">
      <Accordion type="single" collapsible className="w-full">
        {filteredArrayData.map(({ item, index }) => {
          const itemLabel = item[labelField] || item.name || `Item ${index}`;
          const itemKey = item.stop_code || item.station_id || item.destination_name || index;
          
          // Filter item fields based on search (if showAll, show all fields)
          const filteredItemFields = showAll 
            ? itemFields.filter(field => !field.includes('.')) // Exclude nested fields like "all_lines.formatted"
            : itemFields
                .filter(field => !field.includes('.')) // Exclude nested fields like "all_lines.formatted"
                .filter(field => !searchQuery.trim() || matchesSearch(field, searchQuery));
          
          // Check if all_lines section should be shown
          const showAllLines = item.all_lines && typeof item.all_lines === 'object' && 
            (showAll || !searchQuery.trim() || matchesSearch("all_lines", searchQuery) || 
             ["formatted", "next_arrival"].some(field => matchesSearch(field, searchQuery)));
          
          // Filter sub-arrays (if showAll, show all sub-arrays)
          const filteredSubArrays = showAll
            ? Object.entries(subArrays).filter(([subArrayName]) => {
                const subArrayData = item[subArrayName];
                return !!subArrayData;
              })
            : Object.entries(subArrays).filter(([subArrayName]) => {
                const subArrayData = item[subArrayName];
                if (!subArrayData) return false;
                if (!searchQuery.trim()) return true;
                return matchesSearch(subArrayName, searchQuery) || 
                       Object.keys(subArrayData).some(key => matchesSearch(key, searchQuery));
              });

          // Only show item if it has matching content
          const hasMatchingContent = filteredItemFields.length > 0 || showAllLines || filteredSubArrays.length > 0;
          if (!hasMatchingContent) return null;
          
          return (
            <AccordionItem key={itemKey} value={`${arrayName}-${index}`} className="border-b-0">
              <AccordionTrigger className="py-2 hover:no-underline">
                <div className="flex items-center gap-2 text-xs">
                  {icon}
                  <div className="text-left">
                    <div className="font-medium">{itemLabel}</div>
                    <div className="text-muted-foreground text-xs">
                      {item.line || item.destination_name || item.station_name || ""} • Index: {index}
                    </div>
                  </div>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-3 pt-2 pl-2">
                  {/* Item-level variables */}
                  {filteredItemFields.length > 0 && (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1.5">Item Info</p>
                      <div className="flex flex-wrap gap-1.5">
                        {filteredItemFields.map((field) => {
                          const varValue = `{{${pluginId}.${arrayName}.${index}.${field}}}`;
                          return (
                            <VariablePill
                              key={field}
                              label={field}
                              value={varValue}
                              onInsert={() => onInsert(varValue)}
                            />
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Handle special fields like "all_lines" for MUNI */}
                  {showAllLines && (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1.5">All Lines (Combined)</p>
                      <div className="flex flex-wrap gap-1.5">
                        {["formatted", "next_arrival"]
                          .filter(field => showAll || !searchQuery.trim() || matchesSearch(field, searchQuery))
                          .map((field) => {
                            const varValue = `{{${pluginId}.${arrayName}.${index}.all_lines.${field}}}`;
                            return (
                              <VariablePill
                                key={field}
                                label={field}
                                value={varValue}
                                onInsert={() => onInsert(varValue)}
                              />
                            );
                          })}
                      </div>
                    </div>
                  )}

                  {/* Render sub-arrays (e.g., lines within stops) */}
                  {filteredSubArrays.map(([subArrayName, subArraySchema]) => {
                    const subArrayData = item[subArrayName];
                    if (!subArrayData) return null;

                    return (
                      <div key={subArrayName}>
                        {renderSubArraySection(
                          pluginId,
                          index,
                          arrayName,
                          subArrayName,
                          subArrayData,
                          manifest,
                          onInsert,
                          searchQuery,
                          showAll,
                          icon
                        )}
                      </div>
                    );
                  })}
                </div>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </div>
  );
}

export function VariablePickerContent({ onInsert }: VariablePickerContentProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const { data: templateVars, isLoading: isLoadingVars } = useQuery({
    queryKey: ["template-variables"],
    queryFn: api.getTemplateVariables,
  });

  // Determine which plugins are enabled
  const enabledPlugins = useMemo(() => {
    if (!templateVars?.variables) return [];
    return Object.keys(templateVars.variables);
  }, [templateVars]);

  // Fetch plugin manifests for enabled plugins
  const manifestQueries = useQueries({
    queries: enabledPlugins.map((pluginId) => ({
      queryKey: ["plugin-manifest", pluginId],
      queryFn: () => api.getPluginManifest(pluginId),
      enabled: !!pluginId,
      retry: 1, // Only retry once for faster failure
    })),
  });

  // Check if manifests are still loading
  const isLoadingManifests = manifestQueries.some(query => query.isLoading);

  // Extract manifests into a map
  const manifests = useMemo(() => {
    const map: Record<string, PluginManifest | undefined> = {};
    manifestQueries.forEach((query, index) => {
      if (query.data) {
        map[enabledPlugins[index]] = query.data;
      }
    });
    return map;
  }, [manifestQueries, enabledPlugins]);

  // Fetch display data for plugins that have arrays
  const pluginsWithArrays = useMemo(() => {
    return enabledPlugins.filter(pluginId => hasNestedArrays(manifests[pluginId]));
  }, [enabledPlugins, manifests]);

  const { data: pluginDisplayData } = useQuery({
    queryKey: ["plugin-displays-batch", pluginsWithArrays],
    queryFn: () => api.getDisplaysRawBatch(pluginsWithArrays),
    refetchInterval: 30000,
    enabled: pluginsWithArrays.length > 0,
  });

  // Extract plugin data from batch response
  const pluginData = useMemo(() => {
    const data: Record<string, any> = {};
    if (pluginDisplayData?.displays) {
      pluginsWithArrays.forEach((pluginId) => {
        const display = pluginDisplayData.displays[pluginId];
        if (display?.data) {
          data[pluginId] = display.data;
        }
      });
    }
    return data;
  }, [pluginDisplayData, pluginsWithArrays]);

  // Use deferred values for performance
  const deferredPluginData = useDeferredValue(pluginData);

  if (isLoadingVars || isLoadingManifests) {
    return (
      <div className="p-3 min-w-[300px]">
        <Skeleton className="h-4 w-full mb-2" />
        <Skeleton className="h-4 w-3/4 mb-2" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    );
  }

  if (!templateVars?.variables) {
    return (
      <div className="p-3 text-sm text-muted-foreground min-w-[300px]">
        No variables available
      </div>
    );
  }

  // Group variables by category
  const categories = Object.entries(templateVars.variables);

  // Filter categories based on search query (more permissive - if category matches, show all)
  const filteredCategories = categories.filter(([category, vars]) => {
    if (!searchQuery.trim()) return true;
    
    const normalizedQuery = searchQuery.toLowerCase();
    const categoryLower = category.toLowerCase();
    const categoryWords = categoryLower.replace(/_/g, ' ').split(/\s+/);
    
    // If search query matches category name (or any word in it), show ALL variables in that category
    if (matchesSearch(category, searchQuery) || 
        categoryWords.some(word => word.includes(normalizedQuery)) ||
        normalizedQuery.includes(categoryLower) ||
        categoryLower.includes(normalizedQuery)) {
      return true;
    }
    
    const manifest = manifests[category];
    const hasArrays = hasNestedArrays(manifest);
    const arrayName = hasArrays ? getArrayName(manifest) : null;
    const arrayData = arrayName && deferredPluginData[category]?.[arrayName];

    // Filter out nested variables (those with dots, like "stations.0.field")
    // Keep only top-level variables for the category
    const simpleVars = vars.filter(v => {
      // If variable doesn't have a dot, it's top-level
      if (!v.includes('.')) return true;
      // If it starts with category., check if it's nested (has more dots after)
      if (v.startsWith(category + '.')) {
        const afterCategory = v.slice(category.length + 1);
        // If there's no dot after the category prefix, it's a simple field
        return !afterCategory.includes('.');
      }
      return false;
    });

    // Filter out array variables from simple vars
    const generalVars = arrayName 
      ? simpleVars.filter(v => !v.startsWith(arrayName + '.'))
      : simpleVars;

    // Check if any general variable matches (using permissive matching)
    if (generalVars.some(v => matchesVariablePath(category, v, searchQuery))) return true;

    // Check if array name matches
    if (arrayName && matchesSearch(arrayName, searchQuery)) return true;

    // Check if any array items match (if we have array data)
    if (arrayData && arrayData.length > 0) {
      const arraySchema = manifest?.variables?.arrays?.[arrayName];
      if (arraySchema) {
        const itemFields = arraySchema.item_fields || [];
        const hasMatchingArrayItem = arrayData.some((item: any) => {
          const itemLabel = item[arraySchema.label_field || "name"] || item.name || "";
          const secondaryLabel = item.line || item.destination_name || item.station_name || "";
          return (
            matchesSearch(itemLabel, searchQuery) ||
            matchesSearch(secondaryLabel, searchQuery) ||
            itemFields.some(field => matchesSearch(field, searchQuery) || matchesVariablePath(category, field, searchQuery))
          );
        });
        if (hasMatchingArrayItem) return true;
      }
    }

    return false;
  });

  return (
    <div className="w-[350px] flex flex-col">
      {/* Search Input */}
      <div className="p-2 border-b">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            autoFocus
            type="text"
            placeholder="Search variables..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 h-9"
          />
        </div>
      </div>

      <ScrollArea className="h-[400px] flex-1">
        <div className="p-2 space-y-3">
          {filteredCategories.length === 0 ? (
            <div className="p-3 text-sm text-muted-foreground text-center">
              No variables found matching "{searchQuery}"
            </div>
          ) : (
            filteredCategories.map(([category, vars]) => {
              const manifest = manifests[category];
              const hasArrays = hasNestedArrays(manifest);
              const arrayName = hasArrays ? getArrayName(manifest) : null;
              const icon = CATEGORY_ICONS[category];
              
              // Get array data for this plugin
              const arrayData = arrayName && deferredPluginData[category]?.[arrayName];

              // Filter out nested variables (those with dots, like "stations.0.field")
              // Keep only top-level variables for the category
              const simpleVars = vars.filter(v => {
                // If variable doesn't have a dot, it's top-level
                if (!v.includes('.')) return true;
                // If it starts with category., check if it's nested (has more dots after)
                if (v.startsWith(category + '.')) {
                  const afterCategory = v.slice(category.length + 1);
                  // If there's no dot after the category prefix, it's a simple field
                  return !afterCategory.includes('.');
                }
                return false;
              });

              // Filter out array variables from simple vars
              const generalVars = arrayName 
                ? simpleVars.filter(v => !v.startsWith(arrayName + '.'))
                : simpleVars;

              // Check if category name matches search - if so, show ALL variables
              const categoryMatches = searchQuery.trim() && (
                matchesSearch(category, searchQuery) ||
                category.toLowerCase().replace(/_/g, ' ').split(/\s+/).some(word => 
                  word.includes(searchQuery.toLowerCase())
                )
              );

              // Filter general variables based on search (if category matches, show all)
              const filteredGeneralVars = categoryMatches 
                ? generalVars 
                : generalVars.filter(v => 
                    !searchQuery.trim() || matchesVariablePath(category, v, searchQuery)
                  );

              // Check if array section has matches (more permissive - if category matches, show all)
              const hasArrayMatches = hasArrays && arrayName && (
                !searchQuery.trim() || 
                categoryMatches ||
                matchesSearch(arrayName, searchQuery) ||
                (arrayData && arrayData.length > 0 && arrayData.some((item: any) => {
                  const arraySchema = manifest?.variables?.arrays?.[arrayName];
                  if (!arraySchema) return false;
                  const itemLabel = item[arraySchema.label_field || "name"] || item.name || "";
                  const secondaryLabel = item.line || item.destination_name || item.station_name || "";
                  const itemFields = arraySchema.item_fields || [];
                  return (
                    matchesSearch(itemLabel, searchQuery) ||
                    matchesSearch(secondaryLabel, searchQuery) ||
                    itemFields.some(field => matchesSearch(field, searchQuery) || matchesVariablePath(category, field, searchQuery))
                  );
                }))
              );

              // Only show category if it has matching content
              const hasMatchingContent = filteredGeneralVars.length > 0 || hasArrayMatches;
              if (!hasMatchingContent) return null;

              return (
                <div key={category} className="space-y-1.5">
                  <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                    {icon}
                    <span>{category.replace(/_/g, ' ')}</span>
                  </div>
                  
                  {/* General/Simple Variables */}
                  {filteredGeneralVars.length > 0 && (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1.5">General</p>
                      <div className="flex flex-wrap gap-1.5">
                        {filteredGeneralVars.map((variable) => {
                          const varValue = `{{${category}.${variable}}}`;
                          return (
                            <VariablePill
                              key={variable}
                              label={variable}
                              value={varValue}
                              onInsert={() => onInsert(varValue)}
                            />
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Array Section (if plugin has arrays) */}
                  {hasArrays && arrayName && (
                    <div className="space-y-1.5">
                      <p className="text-xs text-muted-foreground flex items-center gap-1">
                        {icon}
                        {arrayName.charAt(0).toUpperCase() + arrayName.slice(1)} {arrayData ? `(${arrayData.length})` : "(None configured)"}
                      </p>
                      {renderArraySection(
                        category,
                        arrayName,
                        arrayData,
                        manifest!,
                        onInsert,
                        searchQuery,
                        !!categoryMatches,
                        icon
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
