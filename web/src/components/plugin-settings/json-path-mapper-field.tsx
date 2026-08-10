"use client";

import { Box, Button, Code, Flex, Grid, Input, Label, Stack, Text } from "@fiestaboard/ui";
import { Loader2, Plus, Trash2, Zap } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

import { usePluginId } from "./field-context";
import { JsonTree } from "./json-tree";

/**
 * `generic-data-mapping-helper` was this widget's name before it was a
 * capability. Both names dispatch here so there is no skew window in either
 * direction: a manifest written for an older core keeps getting the real
 * widget, and a manifest written for a newer one degrades to a warning rather
 * than an uninstall. Dropping the alias is a separate, later change.
 */
export const JSON_PATH_MAPPER_WIDGETS = ["json-path-mapper", "generic-data-mapping-helper"];

export function isJsonPathMapper(widget: string | undefined): boolean {
  return widget !== undefined && JSON_PATH_MAPPER_WIDGETS.includes(widget);
}

/**
 * Which settings properties hold the parts of the probe request. The widget
 * knows the *parts* — a URL, a method, headers — and the manifest says which
 * of the plugin's own properties each one lives in.
 *
 * The defaults are the names the first plugin to use this widget happened to
 * pick, so a manifest that predates the `probe` block keeps working untouched.
 */
const DEFAULT_PROBE_FIELDS = {
  url: "url",
  format: "format",
  method: "method",
  headers: "headers",
  body: "body",
} as const;

/**
 * Which key of a stored mapping row holds which of the three things the widget
 * edits. Same idea as `probe`, one level down: core knows a row has a variable
 * name, a path and a fallback; the manifest says what the plugin calls them.
 */
const DEFAULT_ROW_KEYS = {
  variable: "variable",
  path: "path",
  default: "default",
} as const;

type RowPart = keyof typeof DEFAULT_ROW_KEYS;

export type JsonPathMapperUiOptions = {
  probe?: Partial<Record<keyof typeof DEFAULT_PROBE_FIELDS, string>>;
  keys?: Partial<Record<RowPart, string>>;
};

/** One stored mapping row, keyed by whatever the plugin calls its parts. */
type MappingEntry = Record<string, unknown>;

interface JsonPathMapperFieldProps {
  property: { "ui:options"?: JsonPathMapperUiOptions };
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
  /** The whole settings object, so `probe` can resolve the names it maps. */
  allValues: Record<string, unknown>;
}

/**
 * The generic JSON path mapper: probe an endpoint, browse the response, and
 * map paths in it onto this plugin's template variables.
 *
 * Nothing here is specific to a plugin. The two things that used to be — which
 * sibling properties describe the request, and what each mapping row's keys are
 * called — are declared per field in `ui:options`, and the variable namespace
 * shown in the template hint comes from the surrounding
 * `SchemaFormPluginContext`.
 */
export function JsonPathMapperField({ property, value, onChange, disabled, allValues }: JsonPathMapperFieldProps) {
  const t = useTranslations("schemaForm");
  const pluginId = usePluginId();
  const [previewData, setPreviewData] = useState<unknown>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const probeFields = { ...DEFAULT_PROBE_FIELDS, ...(property["ui:options"]?.probe ?? {}) };
  const rowKeys = { ...DEFAULT_ROW_KEYS, ...(property["ui:options"]?.keys ?? {}) };

  const mappings = (Array.isArray(value) ? value : []) as MappingEntry[];
  const readPart = (row: MappingEntry, part: RowPart): string => {
    const raw = row?.[rowKeys[part]];
    return typeof raw === "string" ? raw : "";
  };

  const handleFetchPreview = async () => {
    const url = (allValues[probeFields.url] as string) || "";
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
        format: (allValues[probeFields.format] as string) || "json",
        method: (allValues[probeFields.method] as string) || "GET",
        headers: (allValues[probeFields.headers] as { name: string; value: string }[]) || [],
        body: (allValues[probeFields.body] as string) || undefined,
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
    const existing = new Set(mappings.map((m) => readPart(m, "variable")));
    let finalVar = sanitised;
    let counter = 2;
    while (existing.has(finalVar)) {
      finalVar = `${sanitised}_${counter++}`;
    }
    const newMappings = [...mappings, newRow({ variable: finalVar, path })];
    onChange(newMappings);
    toast.success(t("addedMapping", { variable: finalVar, path }));
  };

  const newRow = (parts: Partial<Record<RowPart, string>>): MappingEntry => ({
    [rowKeys.variable]: parts.variable ?? "",
    [rowKeys.path]: parts.path ?? "",
    [rowKeys.default]: parts.default ?? "",
  });

  const handleAdd = () => {
    onChange([...mappings, newRow({})]);
  };

  const handleRemove = (index: number) => {
    onChange(mappings.filter((_, i) => i !== index));
  };

  const handleItemChange = (index: number, part: RowPart, val: string) => {
    const next = [...mappings];
    next[index] = { ...next[index], [rowKeys[part]]: val };
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
    <Stack gap="4">
      {/* Test & Preview button */}
      <Flex gap="2">
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
        <Text size="xs" tone="muted" className="self-center">
          {t("testAndPreviewHelp")}
        </Text>
      </Flex>

      {/* Preview error */}
      {previewError && (
        <Text size="xs" tone="destructive" className="bg-destructive/10 rounded-md p-2">
          {previewError}
        </Text>
      )}

      {/* Response tree browser */}
      {previewData && (
        <Box className="border rounded-lg p-3 bg-muted/20 sm:max-h-64 sm:overflow-auto">
          <Text size="xs" weight="medium" tone="muted" className="mb-2">
            {t("responseClickToAdd")}
          </Text>
          <JsonTree data={previewData} path="" onSelect={handlePathSelect} defaultExpanded={true} />
        </Box>
      )}

      {/* Mapping rows */}
      {mappings.map((mapping, index) => {
        const preview = resolvePreview(readPart(mapping, "path"));
        return (
          <Flex key={index} gap="2">
            <Grid gap="2" className="flex-1 p-3 border rounded-lg bg-muted/30">
              <Grid cols="2" gap="2">
                <Grid gap="1">
                  <Label htmlFor={`mapping-${index}-variable`} className="text-xs">
                    {t("variableName")}
                  </Label>
                  <Input
                    id={`mapping-${index}-variable`}
                    value={readPart(mapping, "variable")}
                    onChange={(e) => handleItemChange(index, "variable", e.target.value)}
                    placeholder={t("variableNamePlaceholder")}
                    disabled={disabled}
                    className="h-8 text-sm"
                  />
                </Grid>
                <Grid gap="1">
                  <Label htmlFor={`mapping-${index}-path`} className="text-xs">
                    {t("dataPath")}
                  </Label>
                  <Input
                    id={`mapping-${index}-path`}
                    value={readPart(mapping, "path")}
                    onChange={(e) => handleItemChange(index, "path", e.target.value)}
                    placeholder={t("dataPathPlaceholder")}
                    disabled={disabled}
                    className="h-8 text-sm"
                  />
                </Grid>
              </Grid>
              <Grid cols="2" gap="2">
                <Grid gap="1">
                  <Label htmlFor={`mapping-${index}-default`} className="text-xs">
                    {t("defaultValue")}
                  </Label>
                  <Input
                    id={`mapping-${index}-default`}
                    value={readPart(mapping, "default")}
                    onChange={(e) => handleItemChange(index, "default", e.target.value)}
                    placeholder={t("defaultValuePlaceholder")}
                    disabled={disabled}
                    className="h-8 text-sm"
                  />
                </Grid>
                {preview !== null && (
                  <Grid gap="1">
                    <Label className="text-xs text-green-700 dark:text-green-400">{t("preview")}</Label>
                    <Flex
                      align="center"
                      className="h-8 text-sm text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-950/30 rounded-md px-2 truncate border border-green-200 dark:border-green-800"
                    >
                      {preview}
                    </Flex>
                  </Grid>
                )}
              </Grid>
              {/* The variable is namespaced by the plugin that declares it,
                  so the hint is only truthful when the form knows which
                  plugin it is rendering. Without that it is omitted rather
                  than guessed at. */}
              {pluginId && (
                <Text size="xs" tone="muted">
                  {t("useInTemplates")}{" "}
                  <Code className="bg-muted px-1 rounded">
                    {`{{${pluginId}.${readPart(mapping, "variable") || "..."}}}`}
                  </Code>
                </Text>
              )}
            </Grid>
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
          </Flex>
        );
      })}

      <Button type="button" variant="outline" size="sm" onClick={handleAdd} disabled={disabled} className="w-full">
        <Plus className="h-4 w-4 mr-2" />
        {t("addMapping")}
      </Button>
    </Stack>
  );
}
