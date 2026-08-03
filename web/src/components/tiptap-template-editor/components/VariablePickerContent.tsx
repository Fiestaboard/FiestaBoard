/**
 * Variable Picker Content - Extensible variable list for toolbar dropdown
 * Automatically detects and renders nested arrays from plugin manifests.
 * Supports rich metadata (descriptions, previews, groups) when available.
 */
"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  Badge,
  Box,
  Code,
  Flex,
  Input,
  ScrollArea,
  Skeleton,
  Stack,
  Text,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@fiestaboard/ui";
import { useQueries, useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import { icons as lucideIcons, Search } from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import type { PluginManifest } from "@/lib/api";
import { api } from "@/lib/api";

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
    <Badge variant="variable" asChild className="px-2.5 py-1 cursor-pointer hover:bg-tag-variable/25">
      <button type="button" onClick={onInsert}>
        {label}
        {preview && (
          <Text as="span" tone="muted" weight="normal" className="ml-1.5 text-[10px] opacity-70">
            {preview.length > 12 ? preview.slice(0, 12) + "…" : preview}
          </Text>
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
  subArrayData: Record<string, Record<string, unknown>> | undefined,
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

  const getItemLabel = (itemData: Record<string, unknown>) =>
    (labelField && itemData[labelField]) || (keyField && itemData[keyField]) || itemData[itemFields[0]];

  const filteredEntries = showAll
    ? Object.entries(subArrayData)
    : Object.entries(subArrayData).filter(([key, itemData]) => {
        if (!searchQuery.trim()) return true;
        const displayKey = keyType === "dynamic" && keyField ? String(itemData[keyField] ?? key) : key;
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
    <Box>
      <Text size="xs" tone="muted" className="mb-1.5 flex items-center gap-1">
        {IconComp && <IconComp className="h-3 w-3" />}
        {subArrayName.charAt(0).toUpperCase() + subArrayName.slice(1)} ({filteredEntries.length})
      </Text>
      <Accordion type="single" collapsible className="w-full">
        {filteredEntries.map(([key, itemData]) => {
          const displayKey = keyType === "dynamic" && keyField ? String(itemData[keyField] ?? key) : key;
          const itemLabel = getItemLabel(itemData) ?? displayKey;
          const filteredFields = showAll
            ? itemFields
            : itemFields.filter((field: string) => !searchQuery.trim() || matchesSearch(field, searchQuery));

          if (filteredFields.length === 0) return null;

          return (
            <AccordionItem
              key={key}
              value={`${parentArrayName}-${parentIndex}-${subArrayName}-${key}`}
              className="border-b-0"
            >
              <AccordionTrigger className="py-1.5 hover:no-underline text-xs">
                <Flex align="center" gap="2">
                  {keyType === "dynamic" && (
                    <Badge variant="outline" className="text-[10px] font-mono px-1.5">
                      {displayKey}
                    </Badge>
                  )}
                  <Text as="span" size="xs" className="text-left">
                    {itemLabel}
                  </Text>
                </Flex>
              </AccordionTrigger>
              <AccordionContent>
                <Stack gap="2" className="pt-2 pl-2">
                  <Flex wrap gap="1.5">
                    {filteredFields.map((field: string) => {
                      const varValue = `{{${pluginId}.${parentArrayName}.${parentIndex}.${subArrayName}.${key}.${field}}}`;
                      return (
                        <VariablePill key={field} label={field} value={varValue} onInsert={() => onInsert(varValue)} />
                      );
                    })}
                  </Flex>
                  <Box className="text-xs text-muted-foreground bg-muted/50 p-2 rounded">
                    <Code className="text-xs bg-transparent px-0">
                      {parentArrayName}.{parentIndex}.{subArrayName}.{key}.*
                    </Code>
                  </Box>
                </Stack>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </Box>
  );
}

function renderArraySection(
  pluginId: string,
  arrayName: string,
  arrayData: Record<string, unknown>[] | undefined,
  manifest: PluginManifest,
  onInsert: (variable: string) => void,
  searchQuery: string,
  showAll: boolean = false,
  IconComp?: LucideIcon | null,
  t?: ReturnType<typeof useTranslations>,
) {
  if (!arrayData || arrayData.length === 0) {
    return (
      <Box className="p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground">
        <Text size="xs" tone="muted" className="mb-2">
          {t ? t("configureHint", { arrayName }) : `Configure ${arrayName} in Settings to see indexed variables here.`}
        </Text>
        <Text tone="muted" className="font-mono text-[10px]">
          {t ? t("configureExample") : "Example:"}{" "}
          <Code className="bg-background px-1 text-[10px]">{arrayName}.0.*</Code>
        </Text>
      </Box>
    );
  }

  const arraySchema = manifest.variables.arrays?.[arrayName];
  if (!arraySchema) return null;

  const labelField = arraySchema.label_field || "name";
  const itemFields = arraySchema.item_fields || [];
  const subArrays = arraySchema.sub_arrays || {};

  const filteredArrayData = showAll
    ? arrayData.map((item, index) => ({ item, index }))
    : arrayData
        .map((item, index) => ({ item, index }))
        .filter(({ item, index }) => {
          if (!searchQuery.trim()) return true;
          const itemLabel = String(item[labelField] || item.name || `Item ${index}`);
          return (
            matchesSearch(arrayName, searchQuery) ||
            matchesSearch(itemLabel, searchQuery) ||
            itemFields.some((field: string) => matchesSearch(field, searchQuery)) ||
            Object.keys(subArrays).some((subArrayName) => {
              const subArrayData = item[subArrayName] as Record<string, unknown> | undefined;
              if (!subArrayData) return false;
              return (
                matchesSearch(subArrayName, searchQuery) ||
                Object.keys(subArrayData).some((key) => matchesSearch(key, searchQuery))
              );
            })
          );
        });

  if (filteredArrayData.length === 0) {
    return (
      <Box className="p-3 bg-muted/30 rounded-lg text-xs text-muted-foreground">
        <Text size="xs" tone="muted">
          No matching variables found.
        </Text>
      </Box>
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
            return (
              matchesSearch(subArrayName, searchQuery) ||
              Object.keys(subArrayData).some((key) => matchesSearch(key, searchQuery))
            );
          });

          const hasMatchingContent = filteredItemFields.length > 0 || filteredSubArrays.length > 0;
          if (!hasMatchingContent) return null;

          return (
            <AccordionItem key={index} value={`${arrayName}-${index}`} className="border-b-0">
              <AccordionTrigger className="py-2 hover:no-underline">
                <Flex align="center" gap="2" className="text-xs">
                  {IconComp && <IconComp className="h-3 w-3" />}
                  <Box className="text-left">
                    <Text size="xs" weight="medium">
                      {itemLabel}
                    </Text>
                    <Text size="xs" tone="muted">
                      {t ? t("indexLabel", { index }) : `Index: ${index}`}
                    </Text>
                  </Box>
                </Flex>
              </AccordionTrigger>
              <AccordionContent>
                <Stack gap="3" className="pt-2 pl-2">
                  {filteredItemFields.length > 0 && (
                    <Box>
                      <Text size="xs" tone="muted" className="mb-1.5">
                        {t ? t("itemInfo") : "Item Info"}
                      </Text>
                      <Flex wrap gap="1.5">
                        {filteredItemFields.map((field: string) => {
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
                      </Flex>
                    </Box>
                  )}

                  {filteredSubArrays.map(([subArrayName]) => {
                    const subArrayData = item[subArrayName];
                    if (!subArrayData) return null;
                    return (
                      <Box key={subArrayName}>
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
                          IconComp,
                        )}
                      </Box>
                    );
                  })}
                </Stack>
              </AccordionContent>
            </AccordionItem>
          );
        })}
      </Accordion>
    </ScrollArea>
  );
}

export function VariablePickerContent({
  onInsert,
  maxHeight = "400px",
  autoFocusSearch = true,
  className,
}: VariablePickerContentProps) {
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
    const data: Record<string, Record<string, unknown>> = {};
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
      <Box className="p-3 min-w-[300px]">
        <Skeleton className="h-4 w-full mb-2" />
        <Skeleton className="h-4 w-3/4 mb-2" />
        <Skeleton className="h-4 w-1/2" />
      </Box>
    );
  }

  if (!templateVars?.variables) {
    return (
      <Text tone="muted" className="p-3 min-w-[300px]">
        {t("noVariablesAvailable")}
      </Text>
    );
  }

  const categories = Object.entries(templateVars.variables);

  const filteredCategories = categories.filter(([category, vars]) => {
    if (!searchQuery.trim()) return true;

    const q = searchQuery.toLowerCase();
    const cLower = category.toLowerCase();

    if (
      matchesSearch(category, searchQuery) ||
      cLower
        .replace(/_/g, " ")
        .split(/\s+/)
        .some((w) => w.includes(q))
    ) {
      return true;
    }

    const manifest = manifests[category];
    const arrayNames = getArrayNames(manifest);
    const simpleVars = vars.filter((v) => !v.includes(".") || !v.includes(".*."));
    const generalVars =
      arrayNames.length > 0 ? simpleVars.filter((v) => !arrayNames.some((a) => v.startsWith(a + "."))) : simpleVars;

    if (generalVars.some((v) => matchesVariablePath(category, v, searchQuery))) return true;
    if (arrayNames.some((a) => matchesSearch(a, searchQuery))) return true;

    for (const arrayName of arrayNames) {
      const arrayData = deferredPluginData[category]?.[arrayName];
      if (arrayData && arrayData.length > 0) {
        const arraySchema = manifest?.variables?.arrays?.[arrayName];
        if (arraySchema) {
          const hasMatch = (arrayData as Record<string, unknown>[]).some((item) => {
            const itemLabel = String(item[arraySchema.label_field || "name"] || "");
            return (
              matchesSearch(itemLabel, searchQuery) ||
              arraySchema.item_fields.some((f: string) => matchesSearch(f, searchQuery))
            );
          });
          if (hasMatch) return true;
        }
      }
    }

    return false;
  });

  return (
    <TooltipProvider delayDuration={300}>
      <Flex direction="col" className={`w-full min-w-[min(340px,calc(100vw-24px))]${className ? ` ${className}` : ""}`}>
        <Box className="p-2 border-b">
          <Box className="relative">
            <Search className="absolute left-2.5 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              autoFocus={autoFocusSearch}
              type="text"
              placeholder={t("searchPlaceholder")}
              aria-label={t("searchPlaceholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 h-9"
            />
          </Box>
        </Box>

        <ScrollArea className="flex-1" style={{ height: maxHeight }}>
          <Stack gap="3" className="p-2">
            {filteredCategories.length === 0 ? (
              <Text tone="muted" className="p-3 text-center">
                {t("noVariablesFound", { searchQuery })}
              </Text>
            ) : (
              filteredCategories.map(([category, vars]) => {
                const manifest = manifests[category];
                const arrayNames = getArrayNames(manifest);
                const pluginMeta = variableMetadata[category] ?? {};
                const pluginGroups = variableGroups[category] ?? {};
                const hasGroups = Object.keys(pluginGroups).length > 0;

                const IconComp = resolveIcon(manifest?.icon);

                const simpleVars = vars.filter((v) => !v.includes(".*."));
                const generalVars =
                  arrayNames.length > 0
                    ? simpleVars.filter((v) => !arrayNames.some((a) => v === a || v.startsWith(a + ".")))
                    : simpleVars;

                const categoryMatches =
                  searchQuery.trim() &&
                  (matchesSearch(category, searchQuery) ||
                    category
                      .toLowerCase()
                      .replace(/_/g, " ")
                      .split(/\s+/)
                      .some((w) => w.includes(searchQuery.toLowerCase())));

                const filteredGeneralVars = categoryMatches
                  ? generalVars
                  : generalVars.filter((v) => !searchQuery.trim() || matchesVariablePath(category, v, searchQuery));

                const hasArrayMatches =
                  arrayNames.length > 0 &&
                  arrayNames.some((arrayName) => {
                    if (!searchQuery.trim() || categoryMatches) return true;
                    if (matchesSearch(arrayName, searchQuery)) return true;
                    const arrayData = deferredPluginData[category]?.[arrayName];
                    if (!arrayData || arrayData.length === 0) return false;
                    const arraySchema = manifest?.variables?.arrays?.[arrayName];
                    if (!arraySchema) return false;
                    return (arrayData as Record<string, unknown>[]).some((item) => {
                      const label = String(item[arraySchema.label_field || "name"] || "");
                      return (
                        matchesSearch(label, searchQuery) ||
                        arraySchema.item_fields.some((f: string) => matchesSearch(f, searchQuery))
                      );
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
                  <Stack key={category} gap="1.5">
                    <Flex align="center" gap="2" className="bg-muted/30 rounded px-2 py-1.5 -mx-1">
                      {IconComp && <IconComp className="h-3 w-3 text-muted-foreground" />}
                      <Text as="span" size="xs" weight="semibold">
                        {category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                      </Text>
                    </Flex>

                    {/* Grouped variables */}
                    {hasGroups ? (
                      <>
                        {Object.entries(pluginGroups).map(([groupId, groupDef]) => {
                          const groupVars = groupedVars[groupId];
                          if (!groupVars || groupVars.length === 0) return null;
                          return (
                            <Box key={groupId}>
                              <Text className="text-[9px] uppercase tracking-widest text-muted-foreground/70 mt-1 mb-1 pb-0.5 border-b border-border/30">
                                {groupDef.label}
                              </Text>
                              <Flex wrap gap="1.5">
                                {groupVars.map(renderVarPill)}
                              </Flex>
                            </Box>
                          );
                        })}
                        {groupedVars["__ungrouped__"] && groupedVars["__ungrouped__"].length > 0 && (
                          <Box>
                            <Text className="text-[9px] uppercase tracking-widest text-muted-foreground/70 mt-1 mb-1 pb-0.5 border-b border-border/30">
                              {t("general")}
                            </Text>
                            <Flex wrap gap="1.5">
                              {groupedVars["__ungrouped__"].map(renderVarPill)}
                            </Flex>
                          </Box>
                        )}
                      </>
                    ) : (
                      filteredGeneralVars.length > 0 && (
                        <Box>
                          <Text className="text-[9px] uppercase tracking-widest text-muted-foreground/70 mt-1 mb-1 pb-0.5 border-b border-border/30">
                            {t("general")}
                          </Text>
                          <Flex wrap gap="1.5">
                            {filteredGeneralVars.map(renderVarPill)}
                          </Flex>
                        </Box>
                      )
                    )}

                    {/* Array Sections -- iterate all arrays */}
                    {arrayNames.map((arrayName) => {
                      const arrayData = deferredPluginData[category]?.[arrayName];
                      const shouldShow =
                        !searchQuery.trim() ||
                        categoryMatches ||
                        matchesSearch(arrayName, searchQuery) ||
                        (arrayData && arrayData.length > 0);
                      if (!shouldShow) return null;

                      return (
                        <Stack key={arrayName} gap="1.5">
                          <Text size="xs" tone="muted" className="flex items-center gap-1">
                            {IconComp && <IconComp className="h-3 w-3" />}
                            {arrayName.charAt(0).toUpperCase() + arrayName.slice(1)}{" "}
                            {arrayData ? `(${arrayData.length})` : "(None configured)"}
                          </Text>
                          {renderArraySection(
                            category,
                            arrayName,
                            arrayData,
                            manifest!,
                            onInsert,
                            searchQuery,
                            !!categoryMatches,
                            IconComp,
                            t,
                          )}
                        </Stack>
                      );
                    })}
                  </Stack>
                );
              })
            )}
          </Stack>
        </ScrollArea>
      </Flex>
    </TooltipProvider>
  );
}
