/**
 * Variable Picker Content - Extensible variable list for toolbar dropdown
 * Automatically detects and renders nested arrays from plugin manifests.
 * Supports rich metadata (descriptions, previews, groups) when available.
 */
"use client";

import { useQuery, useQueries } from "@tanstack/react-query";
import { useMemo, useDeferredValue, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { api, PluginManifest } from "@/lib/api";
import { Search, icons as lucideIcons } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";

interface VariablePickerContentProps {
  onInsert: (variable: string) => void;
  maxHeight?: string;
  autoFocusSearch?: boolean;
  /** Extra classes applied to the root div — use to override min-width in constrained layouts */
  className?: string;
}

function resolveIcon(iconName: string | undefined): LucideIcon | null {
  if (!iconName) return null;
  const pascalName = iconName
    .split(/[-_]/)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join("");
  return (lucideIcons as Record<string, LucideIcon>)[pascalName] ?? null;
}

function VariablePill({
  label,
  description,
  preview,
  onInsert,
}: {
  label: string;
  value: string;
  description?: string;
  preview?: string;
  onInsert: () => void;
}) {
  const pill = (
    <Badge
      variant="variable"
      asChild
      className="px-2.5 py-1 cursor-pointer hover:bg-tag-variable/25"
    >
      <button type="button" onClick={onInsert}>
        {label}
        {preview && (
          <span className="ml-1.5 text-muted-foreground font-normal text-[10px] opacity-70">
            {preview.length > 12 ? preview.slice(0, 12) + "…" : preview}
          </span>
        )}
      </button>
    </Badge>
  );

  if (description) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{pill}</TooltipTrigger>
        <TooltipContent side="top" className="max-w-[220px] text-xs">
          {description}
        </TooltipContent>
      </Tooltip>
    );
  }

  return pill;
}

function hasNestedArrays(manifest: PluginManifest | undefined): boolean {
  if (!manifest?.variables?.arrays) return false;
  return Object.keys(manifest.variables.arrays).length > 0;
}

function getArrayNames(manifest: PluginManifest | undefined): string[] {
  if (!manifest?.variables?.arrays) return [];
  return Object.keys(manifest.variables.arrays);
}

function matchesSearch(text: string, searchQuery: string): boolean {
  if (!searchQuery.trim()) return true;
  return text.toLowerCase().includes(searchQuery.toLowerCase());
}

function matchesVariablePath(category: string, variable: string, searchQuery: string): boolean {
  if (!searchQuery.trim()) return true;
  const q = searchQuery.toLowerCase();
  const c = category.toLowerCase();
  const v = variable.toLowerCase();
  return (
    c.includes(q) ||
    v.includes(q) ||
    `${c}.${v}`.includes(q) ||
    c.split(/[._-]/).some((w) => w.includes(q)) ||
    v.split(/[._-]/).some((w) => w.includes(q))
  );
}

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
  IconComp?: LucideIcon | null,
) {
  if (!subArrayData || Object.keys(subArrayData).length === 0) return null;

  const subArraySchema = manifest.variables.arrays?.[parentArrayName]?.sub_arrays?.[subArrayName];
  if (!subArraySchema) return null;

  const itemFields = subArraySchema.item_fields || [];
  const keyType = subArraySchema.key_type || "index";
  const keyField = subArraySchema.key_field;
  const labelField = subArraySchema.label_field;

  const getItemLabel = (itemData: any) =>
    (labelField && itemData[labelField]) || (keyField && itemData[keyField]) || itemData[itemFields[0]];

  const filteredEntries = showAll
    ? Object.entries(subArrayData)
    : Object.entries(subArrayData).filter(([key, itemData]: [string, any]) => {
        if (!searchQuery.trim()) return true;
        const displayKey = keyType === "dynamic" && keyField ? (itemData[keyField] || key) : key;
        const displayValue = getItemLabel(itemData) ?? displayKey;
        return (
          matchesSearch(subArrayName, searchQuery) ||
          matchesSearch(displayKey, searchQuery) ||
          matchesSearch(String(displayValue), searchQuery) ||
          itemFields.some((field: string) => matchesSearch(field, searchQuery))
        );
      });

  if (filteredEntries.length === 0) return null;

  return (
    <div>
      <p className="text-xs text-muted-foreground mb-1.5 flex items-center gap-1">
        {IconComp && <IconComp className="h-3 w-3" />}
        {subArrayName.charAt(0).toUpperCase() + subArrayName.slice(1)} ({filteredEntries.length})
      </p>
      <Accordion type="single" collapsible className="w-full">
        {filteredEntries.map(([key, itemData]: [string, any]) => {
          const displayKey = keyType === "dynamic" && keyField ? (itemData[keyField] || key) : key;
          const itemLabel = getItemLabel(itemData) ?? displayKey;
          const filteredFields = showAll
            ? itemFields
            : itemFields.filter((field: string) => !searchQuery.trim() || matchesSearch(field, searchQuery));

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
                  <span className="text-left">{itemLabel}</span>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-2 pt-2 pl-2">
                  <div className="flex flex-wrap gap-1.5">
                    {filteredFields.map((field: string) => {
                      const varValue = `{{${pluginId}.${parentArrayName}.${parentIndex}.${subArrayName}.${key}.${field}}}`;
                      return (
                        <VariablePill key={field} label={field} value={varValue} onInsert={() => onInsert(varValue)} />
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

function renderArraySection(
  pluginId: string,
  arrayName: string,
  arrayData: any[] | undefined,
  manifest: PluginManifest,
  onInsert: (variable: string) => void,
  searchQuery: string,
  showAll: boolean = false,
  IconComp?: LucideIcon | null,
  t?: ReturnType<typeof useTranslations>,
) {
  if (!arrayData || arrayData.length === 0) {
    return (
      <div className="p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground">
        <p className="mb-2">{t ? t("configureHint", { arrayName }) : `Configure ${arrayName} in Settings to see indexed variables here.`}</p>
        <p className="font-mono text-[10px]">
          {t ? t("configureExample") : "Example:"} <code className="bg-background px-1 rounded">{arrayName}.0.*</code>
        </p>
      </div>
    );
  }

  const arraySchema = manifest.variables.arrays?.[arrayName];
  if (!arraySchema) return null;

  const labelField = arraySchema.label_field || "name";
  const itemFields = arraySchema.item_fields || [];
  const subArrays = arraySchema.sub_arrays || {};

  const filteredArrayData = showAll
    ? arrayData.map((item: any, index: number) => ({ item, index }))
    : arrayData
        .map((item: any, index: number) => ({ item, index }))
        .filter(({ item, index }) => {
          if (!searchQuery.trim()) return true;
          const itemLabel = item[labelField] || item.name || `Item ${index}`;
          return (
            matchesSearch(arrayName, searchQuery) ||
            matchesSearch(itemLabel, searchQuery) ||
            itemFields.some((field: string) => matchesSearch(field, searchQuery)) ||
            Object.keys(subArrays).some((subArrayName) => {
              const subArrayData = item[subArrayName];
              if (!subArrayData) return false;
              return matchesSearch(subArrayName, searchQuery) || Object.keys(subArrayData).some((key) => matchesSearch(key, searchQuery));
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
    <ScrollArea className="max-h-[400px] pr-1">
      <Accordion type="single" collapsible className="w-full">
        {filteredArrayData.map(({ item, index }) => {
          const itemLabel = item[labelField] || item.name || `Item ${index}`;

          const filteredItemFields = showAll
            ? itemFields.filter((field: string) => !field.includes("."))
            : itemFields
                .filter((field: string) => !field.includes("."))
                .filter((field: string) => !searchQuery.trim() || matchesSearch(field, searchQuery));

          const filteredSubArrays = Object.entries(subArrays).filter(([subArrayName]) => {
            const subArrayData = item[subArrayName];
            if (!subArrayData) return false;
            if (showAll || !searchQuery.trim()) return true;
            return matchesSearch(subArrayName, searchQuery) || Object.keys(subArrayData).some((key) => matchesSearch(key, searchQuery));
          });

          const hasMatchingContent = filteredItemFields.length > 0 || filteredSubArrays.length > 0;
          if (!hasMatchingContent) return null;

          return (
            <AccordionItem key={index} value={`${arrayName}-${index}`} className="border-b-0">
              <AccordionTrigger className="py-2 hover:no-underline">
                <div className="flex items-center gap-2 text-xs">
                  {IconComp && <IconComp className="h-3 w-3" />}
                  <div className="text-left">
                    <div className="font-medium">{itemLabel}</div>
                    <div className="text-muted-foreground text-xs">{t ? t("indexLabel", { index }) : `Index: ${index}`}</div>
                  </div>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-3 pt-2 pl-2">
                  {filteredItemFields.length > 0 && (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1.5">{t ? t("itemInfo") : "Item Info"}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {filteredItemFields.map((field: string) => {
                          const varValue = `{{${pluginId}.${arrayName}.${index}.${field}}}`;
                          return <VariablePill key={field} label={field} value={varValue} onInsert={() => onInsert(varValue)} />;
                        })}
                      </div>
                    </div>
                  )}

                  {filteredSubArrays.map(([subArrayName]) => {
                    const subArrayData = item[subArrayName];
                    if (!subArrayData) return null;
                    return (
                      <div key={subArrayName}>
                        {renderSubArraySection(pluginId, index, arrayName, subArrayName, subArrayData, manifest, onInsert, searchQuery, showAll, IconComp)}
                      </div>
                    );
                  })}
                </div>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </ScrollArea>
  );
}

export function VariablePickerContent({ onInsert, maxHeight = "400px", autoFocusSearch = true, className }: VariablePickerContentProps) {
  const t = useTranslations("variablePicker");
  const [searchQuery, setSearchQuery] = useState("");

  const { data: templateVars, isLoading: isLoadingVars } = useQuery({
    queryKey: ["template-variables"],
    queryFn: api.getTemplateVariables,
  });

  const enabledPlugins = useMemo(() => {
    if (!templateVars?.variables) return [];
    return Object.keys(templateVars.variables);
  }, [templateVars]);

  const manifestQueries = useQueries({
    queries: enabledPlugins.map((pluginId) => ({
      queryKey: ["plugin-manifest", pluginId],
      queryFn: () => api.getPluginManifest(pluginId),
      enabled: !!pluginId,
      retry: 1,
    })),
  });

  const isLoadingManifests = manifestQueries.some((query) => query.isLoading);

  const manifests = useMemo(() => {
    const map: Record<string, PluginManifest | undefined> = {};
    manifestQueries.forEach((query, index) => {
      if (query.data) {
        map[enabledPlugins[index]] = query.data;
      }
    });
    return map;
  }, [manifestQueries, enabledPlugins]);

  const pluginsWithArrays = useMemo(() => {
    return enabledPlugins.filter((pluginId) => hasNestedArrays(manifests[pluginId]));
  }, [enabledPlugins, manifests]);

  const { data: pluginDisplayData } = useQuery({
    queryKey: ["plugin-displays-batch", pluginsWithArrays],
    queryFn: () => api.getDisplaysRawBatch(pluginsWithArrays),
    refetchInterval: 15000,
    enabled: pluginsWithArrays.length > 0,
  });

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

  const deferredPluginData = useDeferredValue(pluginData);

  // Extract metadata and groups from the template variables response
  const variableMetadata = templateVars?.variable_metadata ?? {};
  const variableGroups = templateVars?.variable_groups ?? {};

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
        {t("noVariablesAvailable")}
      </div>
    );
  }

  const categories = Object.entries(templateVars.variables);

  const filteredCategories = categories.filter(([category, vars]) => {
    if (!searchQuery.trim()) return true;

    const q = searchQuery.toLowerCase();
    const cLower = category.toLowerCase();

    if (matchesSearch(category, searchQuery) || cLower.replace(/_/g, " ").split(/\s+/).some((w) => w.includes(q))) {
      return true;
    }

    const manifest = manifests[category];
    const arrayNames = getArrayNames(manifest);
    const simpleVars = vars.filter((v) => !v.includes(".") || (!v.includes(".*.")));
    const generalVars = arrayNames.length > 0 ? simpleVars.filter((v) => !arrayNames.some((a) => v.startsWith(a + "."))) : simpleVars;

    if (generalVars.some((v) => matchesVariablePath(category, v, searchQuery))) return true;
    if (arrayNames.some((a) => matchesSearch(a, searchQuery))) return true;

    for (const arrayName of arrayNames) {
      const arrayData = deferredPluginData[category]?.[arrayName];
      if (arrayData && arrayData.length > 0) {
        const arraySchema = manifest?.variables?.arrays?.[arrayName];
        if (arraySchema) {
          const hasMatch = arrayData.some((item: any) => {
            const itemLabel = item[arraySchema.label_field || "name"] || "";
            return matchesSearch(itemLabel, searchQuery) || arraySchema.item_fields.some((f: string) => matchesSearch(f, searchQuery));
          });
          if (hasMatch) return true;
        }
      }
    }

    return false;
  });

  return (
    <TooltipProvider delayDuration={300}>
      <div className={`w-full min-w-[min(340px,calc(100vw-24px))] flex flex-col${className ? ` ${className}` : ""}`}>
        <div className="p-2 border-b">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              autoFocus={autoFocusSearch}
              type="text"
              placeholder={t("searchPlaceholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 h-9"
            />
          </div>
        </div>

        <ScrollArea className="flex-1" style={{ height: maxHeight }}>
          <div className="p-2 space-y-3">
            {filteredCategories.length === 0 ? (
              <div className="p-3 text-sm text-muted-foreground text-center">
                {t("noVariablesFound", { searchQuery })}
              </div>
            ) : (
              filteredCategories.map(([category, vars]) => {
                const manifest = manifests[category];
                const arrayNames = getArrayNames(manifest);
                const pluginMeta = variableMetadata[category] ?? {};
                const pluginGroups = variableGroups[category] ?? {};
                const hasGroups = Object.keys(pluginGroups).length > 0;

                const IconComp = resolveIcon(manifest?.icon);

                const simpleVars = vars.filter((v) => !v.includes(".*."));
                const generalVars = arrayNames.length > 0
                  ? simpleVars.filter((v) => !arrayNames.some((a) => v === a || v.startsWith(a + ".")))
                  : simpleVars;

                const categoryMatches = searchQuery.trim() && (
                  matchesSearch(category, searchQuery) ||
                  category.toLowerCase().replace(/_/g, " ").split(/\s+/).some((w) => w.includes(searchQuery.toLowerCase()))
                );

                const filteredGeneralVars = categoryMatches
                  ? generalVars
                  : generalVars.filter((v) => !searchQuery.trim() || matchesVariablePath(category, v, searchQuery));

                const hasArrayMatches = arrayNames.length > 0 && arrayNames.some((arrayName) => {
                  if (!searchQuery.trim() || categoryMatches) return true;
                  if (matchesSearch(arrayName, searchQuery)) return true;
                  const arrayData = deferredPluginData[category]?.[arrayName];
                  if (!arrayData || arrayData.length === 0) return false;
                  const arraySchema = manifest?.variables?.arrays?.[arrayName];
                  if (!arraySchema) return false;
                  return arrayData.some((item: any) => {
                    const label = item[arraySchema.label_field || "name"] || "";
                    return matchesSearch(label, searchQuery) || arraySchema.item_fields.some((f: string) => matchesSearch(f, searchQuery));
                  });
                });

                if (filteredGeneralVars.length === 0 && !hasArrayMatches) return null;

                // Group simple variables by their group field (from metadata)
                const groupedVars: Record<string, string[]> = {};
                if (hasGroups) {
                  for (const v of filteredGeneralVars) {
                    const group = pluginMeta[v]?.group || "";
                    const key = group && pluginGroups[group] ? group : "__ungrouped__";
                    (groupedVars[key] ??= []).push(v);
                  }
                }

                const renderVarPill = (variable: string) => {
                  const meta = pluginMeta[variable];
                  const varValue = `{{${category}.${variable}}}`;
                  return (
                    <VariablePill
                      key={variable}
                      label={variable}
                      value={varValue}
                      description={meta?.description}
                      preview={meta?.preview}
                      onInsert={() => onInsert(varValue)}
                    />
                  );
                };

                return (
                  <div key={category} className="space-y-1.5">
                    <div className="flex items-center gap-2 bg-muted/30 rounded px-2 py-1.5 -mx-1">
                      {IconComp && <IconComp className="h-3 w-3 text-muted-foreground" />}
                      <span className="text-xs font-semibold text-foreground">{category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}</span>
                    </div>

                    {/* Grouped variables */}
                    {hasGroups ? (
                      <>
                        {Object.entries(pluginGroups).map(([groupId, groupDef]) => {
                          const groupVars = groupedVars[groupId];
                          if (!groupVars || groupVars.length === 0) return null;
                          return (
                            <div key={groupId}>
                              <p className="text-[9px] uppercase tracking-widest text-muted-foreground/70 mt-1 mb-1 pb-0.5 border-b border-border/30">{groupDef.label}</p>
                              <div className="flex flex-wrap gap-1.5">{groupVars.map(renderVarPill)}</div>
                            </div>
                          );
                        })}
                        {groupedVars["__ungrouped__"] && groupedVars["__ungrouped__"].length > 0 && (
                          <div>
                            <p className="text-[9px] uppercase tracking-widest text-muted-foreground/70 mt-1 mb-1 pb-0.5 border-b border-border/30">{t("general")}</p>
                            <div className="flex flex-wrap gap-1.5">{groupedVars["__ungrouped__"].map(renderVarPill)}</div>
                          </div>
                        )}
                      </>
                    ) : (
                      filteredGeneralVars.length > 0 && (
                        <div>
                          <p className="text-[9px] uppercase tracking-widest text-muted-foreground/70 mt-1 mb-1 pb-0.5 border-b border-border/30">{t("general")}</p>
                          <div className="flex flex-wrap gap-1.5">{filteredGeneralVars.map(renderVarPill)}</div>
                        </div>
                      )
                    )}

                    {/* Array Sections -- iterate all arrays */}
                    {arrayNames.map((arrayName) => {
                      const arrayData = deferredPluginData[category]?.[arrayName];
                      const shouldShow = !searchQuery.trim() || categoryMatches || matchesSearch(arrayName, searchQuery) || (arrayData && arrayData.length > 0);
                      if (!shouldShow) return null;

                      return (
                        <div key={arrayName} className="space-y-1.5">
                          <p className="text-xs text-muted-foreground flex items-center gap-1">
                            {IconComp && <IconComp className="h-3 w-3" />}
                            {arrayName.charAt(0).toUpperCase() + arrayName.slice(1)} {arrayData ? `(${arrayData.length})` : "(None configured)"}
                          </p>
                          {renderArraySection(category, arrayName, arrayData, manifest!, onInsert, searchQuery, !!categoryMatches, IconComp, t)}
                        </div>
                      );
                    })}
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>
      </div>
    </TooltipProvider>
  );
}
