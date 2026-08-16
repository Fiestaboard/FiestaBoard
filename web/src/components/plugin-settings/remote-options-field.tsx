"use client";

import {
  Button,
  Flex,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Trash2 } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { api, type PluginOption, type PluginOptionsResponse } from "@/lib/api";

import { type FieldScope, useFieldScope, usePluginId } from "./field-context";

/** A dependency counts as answered once it holds something other than blank/null. */
function isAnswered(value: unknown): boolean {
  return value !== undefined && value !== null && value !== "";
}

interface Dependencies {
  /** `{dep: value}` for every dependency, sent to the plugin as `parent`. */
  parent: Record<string, unknown>;
  /** Titles of the dependencies still unanswered, in declaration order. */
  missing: string[];
}

/**
 * Resolve `ui:options.depends_on` against the field's own scope first, then the
 * root — a field inside an array item names its siblings in that item, but may
 * also depend on a top-level property such as an account or region.
 */
function resolveDependencies(dependsOn: string[], { scope, root, titles }: FieldScope): Dependencies {
  const parent: Record<string, unknown> = {};
  const missing: string[] = [];
  for (const dep of dependsOn) {
    const resolved = isAnswered(scope[dep]) ? scope[dep] : root[dep];
    parent[dep] = resolved ?? null;
    if (!isAnswered(resolved)) missing.push(titles[dep] || dep);
  }
  return { parent, missing };
}

/**
 * Turn a Select's string value back into the JSON type the schema declares.
 *
 * Base UI Select values are always strings, but the stored config has to keep
 * the plugin's type — an integer `park_id` must persist as `16`, never `"16"`,
 * or the plugin's own lookups miss. When the catalog contains the value we use
 * its raw form verbatim (the most faithful answer); otherwise — a custom or
 * no-longer-listed value — we fall back to the declared `type`.
 */
function coerceToSchemaType(raw: string, type: string | undefined, catalog: PluginOption[]): unknown {
  const match = catalog.find((option) => String(option.value) === raw);
  if (match) return match.value;
  if (type === "integer") {
    const parsed = parseInt(raw, 10);
    return Number.isNaN(parsed) ? raw : parsed;
  }
  if (type === "number") {
    const parsed = parseFloat(raw);
    return Number.isNaN(parsed) ? raw : parsed;
  }
  if (type === "boolean") return raw === "true";
  return raw;
}

/**
 * `get_options()` may hit an upstream API on every keystroke, so server-side
 * search waits for the user to pause rather than firing per character.
 */
const SERVER_SEARCH_DEBOUNCE_MS = 300;

function useDebouncedValue(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

/** Case-insensitive substring match over the two fields the user can read. */
function filterOptions(options: PluginOption[], search: string): PluginOption[] {
  const needle = search.trim().toLowerCase();
  if (!needle) return options;
  return options.filter(
    (option) =>
      option.label.toLowerCase().includes(needle) || (option.description ?? "").toLowerCase().includes(needle),
  );
}

/** The `ui:options` grammar a `remote-options` field may declare. */
export interface RemoteOptionsUiOptions {
  options_id?: string;
  depends_on?: string[];
  multiple?: boolean;
  searchable?: boolean;
  server_search?: boolean;
  reorderable?: boolean;
  allow_custom?: boolean;
  cache_seconds?: number;
  placeholder?: string;
  /**
   * Name of a *sibling* property collecting a short display name per chosen
   * option, keyed by `String(value)`. Multi-select only.
   */
  labels_field?: string;
}

/**
 * Read the stored label map out of the sibling property.
 *
 * A `Map`, not a bare object, so the widget cannot look a label up by a raw
 * numeric value and be rescued by JS coercing the key: stored config arrives
 * from JSON with string keys, and every lookup has to go through
 * {@link optionKey} to find them.
 *
 * Anything that is not a plain object — absent, `null`, a leftover array —
 * reads as empty rather than throwing, because the widget must survive config
 * written before the field existed. Entries whose value is not a string are
 * not display names and are ignored.
 */
function readLabels(stored: unknown): Map<string, string> {
  const labels = new Map<string, string>();
  if (typeof stored !== "object" || stored === null || Array.isArray(stored)) return labels;
  for (const [key, text] of Object.entries(stored as Record<string, unknown>)) {
    if (typeof text === "string") labels.set(key, text);
  }
  return labels;
}

/**
 * The canonical string key for an option value — what the catalog is indexed
 * by, and what a `labels_field` map is keyed by.
 *
 * Explicitly stringified, because the plugin reads the map back with string
 * keys: Disney's does `custom_names.get(str(ride_id))` while its option values
 * are integers. Leaving the raw value in place would happen to survive being
 * written into a JS object — keys coerce — but every lookup the widget itself
 * does would then miss the string keys that came back from stored config.
 */
function optionKey(value: unknown): string {
  return String(value);
}

/** The slice of a JSON-schema property this widget reads. */
export interface RemoteOptionsProperty {
  type?: string;
  title?: string;
  maxItems?: number;
  items?: { type?: string };
  "ui:options"?: RemoteOptionsUiOptions;
}

export interface RemoteOptionsFieldProps {
  name: string;
  property: RemoteOptionsProperty;
  value: unknown;
  /**
   * Commit the field's value, plus — only for `labels_field` — a patch of the
   * sibling properties in the same object, applied in the same update.
   */
  onChange: (value: unknown, siblings?: Record<string, unknown>) => void;
  disabled?: boolean;
}

/** A disabled Select that only states why it cannot offer anything. */
function InertSelect({ id, placeholder }: { id: string; placeholder: string }) {
  return (
    <Select value="" disabled modal={false}>
      <SelectTrigger id={id}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent />
    </Select>
  );
}

export function RemoteOptionsField({ name, property, value, onChange, disabled }: RemoteOptionsFieldProps) {
  const t = useTranslations("schemaForm");
  const pluginId = usePluginId();
  const fieldScope = useFieldScope();
  const ui = property["ui:options"] ?? {};
  const optionsId = ui.options_id ?? "";
  const dependsOn = ui.depends_on ?? [];
  const { parent, missing } = resolveDependencies(dependsOn, fieldScope);
  const dependsSatisfied = missing.length === 0;

  // One search box drives both modes: `searchable` filters what was already
  // fetched, `server_search` sends the text to the plugin (debounced, because
  // `get_options` may hit an upstream API on every keystroke).
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, SERVER_SEARCH_DEBOUNCE_MS);
  const serverSearchQuery = ui.server_search ? debouncedSearch : "";

  const query = useQuery({
    queryKey: ["plugin-options", pluginId, optionsId, parent, serverSearchQuery],
    queryFn: () => api.getPluginOptions(pluginId as string, optionsId, { parent, query: serverSearchQuery }),
    enabled: Boolean(pluginId) && dependsSatisfied,
    staleTime: (ui.cache_seconds ?? 0) * 1000,
  });

  // A value chosen under one parent cannot be assumed to exist under another
  // (stop 13915 is a Muni stop, not an AC Transit one), so moving from one
  // answered parent to a *different* answered parent drops it instead of
  // persisting something the plugin will fail to resolve.
  //
  // Only answered parents are remembered, and that is the whole point: a form
  // may render before its saved config has loaded — `InstalledPluginRow` mounts
  // `SchemaForm` with `{}` and fills it in from a `useEffect` — so a dependency
  // going from *unanswered* to *answered* is hydration, not the user changing
  // anything, and must leave the stored value alone. (Comparing raw parent keys
  // instead deleted the saved child value on every cold dialog open; reopening
  // it in the same session hid the bug, because react-query then had the config
  // cached and the empty first render never happened.) The same rule means
  // clearing a parent keeps the child until a different parent is actually
  // chosen, so a mis-click costs nothing.
  const parentKey = JSON.stringify(parent);
  const multiple = Boolean(ui.multiple);
  const hasValue = multiple ? Array.isArray(value) && value.length > 0 : isAnswered(value);
  // `onChange` gets a new identity every render, so the effect re-runs often;
  // the recorded key is what makes it a no-op unless the parent really moved.
  const lastSatisfiedParentKey = useRef<string | null>(dependsSatisfied ? parentKey : null);
  useEffect(() => {
    if (!dependsSatisfied) return;
    const previous = lastSatisfiedParentKey.current;
    lastSatisfiedParentKey.current = parentKey;
    // `null` is "we have never seen this field scoped" — nothing to invalidate.
    if (previous === null || previous === parentKey) return;
    if (hasValue) onChange(multiple ? [] : undefined);
  }, [dependsSatisfied, parentKey, hasValue, multiple, onChange]);

  const options = query.data?.options ?? [];
  const scalarType = ui.multiple ? property.items?.type : property.type;

  // `labels_field` is the only thing this widget writes outside its own key, so
  // it stays inert unless the manifest asked for it on a multi-select. The map
  // is read straight out of the field's scope on every render and written only
  // from a user action — never from an effect, because an effect would fire on
  // the empty first render of a cold dialog open and wipe saved names.
  const labelsField = multiple && ui.labels_field ? ui.labels_field : undefined;
  const labels = readLabels(labelsField ? fieldScope.scope[labelsField] : undefined);

  // Without a plugin id there is nothing to ask. Say so and stay inert rather
  // than throwing or requesting `/plugins/null/options/…`.
  if (!pluginId) {
    return <InertSelect id={name} placeholder={t("remoteOptionsUnavailable")} />;
  }

  // A catalog that has not been scoped yet is meaningless, so the field waits
  // — visibly, naming what it waits on — and sends nothing.
  if (!dependsSatisfied) {
    return <InertSelect id={name} placeholder={t("remoteOptionsSelectParentFirst", { parent: missing[0] })} />;
  }

  const controlDisabled = disabled || query.isLoading;
  // With `server_search` the plugin has already applied the query, so filtering
  // again locally would only hide rows the plugin deliberately returned.
  const visible = ui.searchable && !ui.server_search ? filterOptions(options, search) : options;

  return (
    <Stack gap="1.5">
      {(ui.searchable || ui.server_search) && (
        <Input
          type="search"
          value={search}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
          aria-label={t("remoteOptionsSearchLabel")}
          placeholder={t("remoteOptionsSearchPlaceholder")}
          disabled={disabled}
          className="h-8 text-sm"
        />
      )}
      {ui.multiple ? (
        <MultiSelectControl
          name={name}
          options={options}
          visible={visible}
          value={Array.isArray(value) ? value : []}
          onChange={onChange}
          disabled={controlDisabled}
          scalarType={scalarType}
          maxItems={property.maxItems}
          reorderable={Boolean(ui.reorderable)}
          placeholder={ui.placeholder}
          labelsField={labelsField}
          labels={labels}
        />
      ) : (
        <SingleSelectControl
          name={name}
          options={options}
          visible={visible}
          value={value}
          onChange={onChange}
          disabled={controlDisabled}
          scalarType={scalarType}
          placeholder={ui.placeholder}
        />
      )}
      {ui.allow_custom && (
        <CustomValueEntry
          multiple={Boolean(ui.multiple)}
          value={value}
          onChange={onChange}
          scalarType={scalarType}
          options={options}
          disabled={disabled}
        />
      )}
      <FieldNotes query={query} serverSearch={Boolean(ui.server_search)} optionCount={options.length} />
    </Stack>
  );
}

/**
 * Free-text entry for `allow_custom`, so a catalog that is merely incomplete
 * (a ticker the search API does not index, a private stop code) does not become
 * a wall the user cannot get past.
 */
function CustomValueEntry({
  multiple,
  value,
  onChange,
  scalarType,
  options,
  disabled,
}: {
  multiple: boolean;
  value: unknown;
  onChange: (value: unknown) => void;
  scalarType: string | undefined;
  options: PluginOption[];
  disabled?: boolean;
}) {
  const t = useTranslations("schemaForm");
  const [text, setText] = useState("");

  const commit = () => {
    const raw = text.trim();
    if (!raw) return;
    const coerced = coerceToSchemaType(raw, scalarType, options);
    if (multiple) {
      const current = Array.isArray(value) ? value : [];
      if (!current.some((item) => String(item) === raw)) onChange([...current, coerced]);
    } else {
      onChange(coerced);
    }
    setText("");
  };

  return (
    <Flex gap="2">
      <Input
        value={text}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setText(e.target.value)}
        aria-label={t("remoteOptionsCustomLabel")}
        placeholder={t("remoteOptionsCustomPlaceholder")}
        disabled={disabled}
        className="h-8 text-sm"
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="shrink-0"
        onClick={commit}
        disabled={disabled || text.trim() === ""}
      >
        {t("remoteOptionsCustomAdd")}
      </Button>
    </Flex>
  );
}

interface ControlProps {
  name: string;
  /** The full catalog, for resolving labels of values that are filtered out. */
  options: PluginOption[];
  /** What search has left to offer. */
  visible: PluginOption[];
  /** Same contract as {@link RemoteOptionsFieldProps.onChange}. */
  onChange: (value: unknown, siblings?: Record<string, unknown>) => void;
  disabled?: boolean;
  scalarType: string | undefined;
  placeholder?: string;
}

/**
 * One dropdown row.
 *
 * The children stay a bare label on purpose: the Select wrapper builds its
 * value→label map from exactly these children and renders the match in the
 * trigger, so a two-line body here would put the description in the trigger
 * too. The secondary text rides along as a tooltip instead.
 */
function optionItem(option: PluginOption) {
  return (
    <SelectItem
      key={String(option.value)}
      value={String(option.value)}
      disabled={option.disabled}
      title={option.description ?? undefined}
    >
      {option.label}
    </SelectItem>
  );
}

function SingleSelectControl({
  name,
  options,
  visible,
  value,
  onChange,
  disabled,
  scalarType,
  placeholder,
}: ControlProps & { value: unknown }) {
  const t = useTranslations("schemaForm");
  const selectedRaw = value === undefined || value === null ? "" : String(value);
  // The selected row must always be rendered, even when search or the plugin
  // has dropped it from the list: the Select resolves the trigger's label from
  // the rendered items, so omitting it would blank a field the user did fill
  // in. A value the catalog never had shows as itself.
  const selectedOption = options.find((option) => String(option.value) === selectedRaw);
  const needsPin = selectedRaw !== "" && !visible.some((option) => String(option.value) === selectedRaw);

  return (
    <Select
      value={selectedRaw}
      onValueChange={(raw) => onChange(coerceToSchemaType(raw, scalarType, options))}
      disabled={disabled}
      modal={false}
    >
      <SelectTrigger id={name}>
        <SelectValue placeholder={placeholder || t("remoteOptionsPlaceholder")} />
      </SelectTrigger>
      <SelectContent className="max-h-[300px] z-[120]">
        {needsPin && <SelectItem value={selectedRaw}>{selectedOption ? selectedOption.label : selectedRaw}</SelectItem>}
        {visible.map(optionItem)}
      </SelectContent>
    </Select>
  );
}

function MultiSelectControl({
  name,
  options,
  visible,
  value,
  onChange,
  disabled,
  scalarType,
  maxItems,
  reorderable,
  placeholder,
  labelsField,
  labels,
}: ControlProps & {
  value: unknown[];
  maxItems?: number;
  reorderable: boolean;
  /** Sibling property collecting per-choice display names, or undefined. */
  labelsField?: string;
  /** Those names as stored, keyed by {@link optionKey}. */
  labels: Map<string, string>;
}) {
  const t = useTranslations("schemaForm");
  const catalogLabels = new Map(options.map((option) => [optionKey(option.value), option.label]));
  const chosen = value.map((item) => optionKey(item));
  const chosenSet = new Set(chosen);
  // Offering an already-chosen option again can only produce a duplicate.
  const available = visible.filter((option) => !chosenSet.has(optionKey(option.value)));
  const atMax = maxItems !== undefined && value.length >= maxItems;
  // Same rule as the single control: an unrecognised stored value shows as
  // itself so a save never silently drops it.
  const labelOf = (raw: string) => catalogLabels.get(raw) ?? raw;

  // The display name and the selection are one edit, committed together — see
  // `FieldProps.onChange`. Only the keys the user actually touched move.
  const setLabel = (raw: string, text: string) => {
    if (!labelsField) return;
    const next = new Map(labels);
    // An empty box means "no custom name", which the *absence* of a key
    // already says — storing "" would only accumulate entries that mean
    // nothing to the plugin.
    if (text === "") next.delete(raw);
    else next.set(raw, text);
    onChange(value, { [labelsField]: Object.fromEntries(next) });
  };

  /**
   * Remove a chosen option, and with it the display name that only existed to
   * describe it. Exactly that one key: names for the rows that stay, and for
   * anything else already in the map, are left as they are.
   */
  const remove = (index: number) => {
    const remaining = value.filter((_, i) => i !== index);
    if (!labelsField) {
      onChange(remaining);
      return;
    }
    const next = new Map(labels);
    next.delete(chosen[index]);
    onChange(remaining, { [labelsField]: Object.fromEntries(next) });
  };

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= value.length) return;
    const next = [...value];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  return (
    <Stack gap="2">
      {chosen.map((raw, index) => (
        <Flex
          key={`${raw}-${index}`}
          align="center"
          gap="1"
          data-testid="remote-options-chosen"
          className="rounded-md border bg-muted/40 px-2 py-1.5"
        >
          <Text as="span" className="flex-1 truncate">
            {labelOf(raw)}
          </Text>
          {labelsField && (
            <Input
              value={labels.get(raw) ?? ""}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLabel(raw, e.target.value)}
              aria-label={t("remoteOptionsLabelFor", { label: labelOf(raw) })}
              placeholder={t("remoteOptionsLabelPlaceholder")}
              disabled={disabled}
              className="h-7 w-32 shrink-0 text-sm"
            />
          )}
          {reorderable && (
            <Flex align="center" className="shrink-0">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                disabled={disabled || index === 0}
                onClick={() => move(index, -1)}
                aria-label={t("remoteOptionsMoveUp", { label: labelOf(raw) })}
              >
                <ArrowUp className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                disabled={disabled || index === chosen.length - 1}
                onClick={() => move(index, 1)}
                aria-label={t("remoteOptionsMoveDown", { label: labelOf(raw) })}
              >
                <ArrowDown className="h-4 w-4" />
              </Button>
            </Flex>
          )}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0 text-destructive hover:text-destructive"
            disabled={disabled}
            onClick={() => remove(index)}
            aria-label={t("remoteOptionsRemove", { label: labelOf(raw) })}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </Flex>
      ))}
      <Select
        value=""
        onValueChange={(raw) => onChange([...value, coerceToSchemaType(raw, scalarType, options)])}
        disabled={disabled || atMax}
        modal={false}
      >
        <SelectTrigger id={name} aria-label={t("remoteOptionsAddLabel")} className="border-dashed">
          <SelectValue placeholder={placeholder || t("remoteOptionsAdd")} />
        </SelectTrigger>
        <SelectContent className="max-h-[300px] z-[120]">{available.map(optionItem)}</SelectContent>
      </Select>
    </Stack>
  );
}

/**
 * The line (or lines) under the control explaining what the catalog is doing.
 *
 * The distinction that matters: a transport failure is an incident and gets
 * destructive framing plus a retry; `data.error` is the plugin saying "ask me
 * later" (no API key yet, upstream down) and gets a quiet hint — never a toast,
 * which would fire repeatedly as the settings dialog refetches.
 */
function FieldNotes({
  query,
  serverSearch,
  optionCount,
}: {
  query: UseQueryResult<PluginOptionsResponse>;
  serverSearch: boolean;
  optionCount: number;
}) {
  const t = useTranslations("schemaForm");

  if (query.isLoading) {
    return (
      <Flex align="center" gap="2" className="text-xs text-muted-foreground">
        <Spinner size="sm" label={null} />
        {t("remoteOptionsLoading")}
      </Flex>
    );
  }

  if (query.isError) {
    return (
      <Flex align="center" gap="2">
        <Text size="xs" tone="destructive">
          {t("remoteOptionsLoadFailed")}
        </Text>
        <Button type="button" variant="outline" size="sm" className="h-6 px-2 text-xs" onClick={() => query.refetch()}>
          {t("remoteOptionsRetry")}
        </Button>
      </Flex>
    );
  }

  const data = query.data;
  if (!data) return null;

  return (
    <Stack gap="1">
      {data.error && (
        <Text size="xs" tone="muted">
          {data.error}
        </Text>
      )}
      {!data.error && optionCount === 0 && (
        <Text size="xs" tone="muted">
          {t("remoteOptionsEmpty")}
        </Text>
      )}
      {data.stale && (
        <Text size="xs" tone="muted">
          {t("remoteOptionsStale")}
        </Text>
      )}
      {/* A cap the user cannot see is indistinguishable from "your option does
          not exist", so every truncated catalog says so. Only `server_search`
          can actually reach the rest — client-side search just filters what
          already arrived — so only it gets the "narrow it down" wording. */}
      {data.has_more && (
        <Text size="xs" tone="muted">
          {serverSearch ? t("remoteOptionsRefineSearch") : t("remoteOptionsTruncated")}
        </Text>
      )}
    </Stack>
  );
}
