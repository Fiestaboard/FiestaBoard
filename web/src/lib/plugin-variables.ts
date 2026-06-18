// Helpers for turning a plugin's manifest `variables` block into the rows shown
// in the Integrations config sheet's "Template Variables" table, and for
// organizing those rows by their declared groups — mirroring how the page
// builder variable picker (VariablePickerContent) groups them.

/** A single declared group, e.g. `{ label: "Time" }`. */
export interface VariableGroupDef {
  label: string;
}

/** Per-variable metadata as declared in the manifest's `variables.simple` map. */
export interface SimpleVariableMeta {
  description?: string;
  type?: string;
  max_length?: number;
  group?: string;
  example?: string;
}

/** Shape of a plugin's manifest `variables` block (as returned by /plugins/{id}). */
export interface VariablesBlock {
  groups?: Record<string, VariableGroupDef>;
  simple?: string[] | Record<string, SimpleVariableMeta>;
  arrays?: Record<string, { label_field: string; item_fields: string[] }>;
}

/** A row in the Template Variables table. */
export interface PluginVariableRow {
  name: string;
  description: string;
  maxChars: number;
  /** Group id from the manifest, when declared. Array-derived rows are ungrouped. */
  group?: string;
}

/** A contiguous section of the table: a declared group, or the ungrouped bucket. */
export interface VariableGroupSection {
  /** Group id, or `null` for the ungrouped ("General") bucket. */
  groupId: string | null;
  label: string;
  rows: PluginVariableRow[];
}

const DEFAULT_MAX_CHARS = 22;

const humanize = (s: string): string => s.replace(/_/g, " ");

/**
 * Flatten a plugin's `variables` block into table rows.
 *
 * Handles both shapes of `variables.simple` (a plain `string[]` or a metadata
 * map) and expands `variables.arrays` into `name.{index}.field` rows. Simple
 * variables carry their declared `group`; array-derived rows have none.
 */
export function buildVariablesList(
  variables: VariablesBlock | undefined,
  maxLengths: Record<string, number> | undefined,
): PluginVariableRow[] {
  if (!variables) return [];

  const rows: PluginVariableRow[] = [];
  const maxFor = (key: string, fallback: number): number => maxLengths?.[key] ?? fallback;

  const { simple, arrays } = variables;

  if (simple) {
    if (Array.isArray(simple)) {
      for (const name of simple) {
        rows.push({
          name,
          description: humanize(name),
          maxChars: maxFor(name, DEFAULT_MAX_CHARS),
          group: undefined,
        });
      }
    } else {
      for (const [name, meta] of Object.entries(simple)) {
        rows.push({
          name,
          description: meta.description ?? humanize(name),
          maxChars: maxFor(name, meta.max_length ?? DEFAULT_MAX_CHARS),
          group: meta.group,
        });
      }
    }
  }

  if (arrays) {
    for (const [arrayName, config] of Object.entries(arrays)) {
      rows.push({
        name: `${arrayName}.{index}.${config.label_field}`,
        description: `${arrayName} label`,
        maxChars: maxFor(`${arrayName}.${config.label_field}`, DEFAULT_MAX_CHARS),
        group: undefined,
      });
      // Skip the label field in item_fields to avoid duplicate keys.
      for (const field of config.item_fields.filter((f) => f !== config.label_field)) {
        rows.push({
          name: `${arrayName}.{index}.${field}`,
          description: `${arrayName} ${humanize(field)}`,
          maxChars: maxFor(`${arrayName}.${field}`, DEFAULT_MAX_CHARS),
          group: undefined,
        });
      }
    }
  }

  return rows;
}

/** The declared groups for a plugin, or an empty object when none are declared. */
export function getVariableGroups(variables: VariablesBlock | undefined): Record<string, VariableGroupDef> {
  return variables?.groups ?? {};
}

/**
 * Organize rows into sections following the manifest's group order, dropping
 * groups with no matching rows. Rows with no group (or a group not declared in
 * `groups`) are collected into a trailing "General" section labelled
 * `generalLabel`. When no groups are declared, every row lands in that single
 * General section.
 */
export function groupVariableRows(
  rows: PluginVariableRow[],
  groups: Record<string, VariableGroupDef>,
  generalLabel: string,
): VariableGroupSection[] {
  const byGroup = new Map<string, PluginVariableRow[]>();
  const ungrouped: PluginVariableRow[] = [];

  for (const row of rows) {
    if (row.group && groups[row.group]) {
      const bucket = byGroup.get(row.group);
      if (bucket) {
        bucket.push(row);
      } else {
        byGroup.set(row.group, [row]);
      }
    } else {
      ungrouped.push(row);
    }
  }

  const sections: VariableGroupSection[] = [];
  for (const [groupId, def] of Object.entries(groups)) {
    const groupRows = byGroup.get(groupId);
    if (groupRows && groupRows.length > 0) {
      sections.push({ groupId, label: def.label, rows: groupRows });
    }
  }
  if (ungrouped.length > 0) {
    sections.push({ groupId: null, label: generalLabel, rows: ungrouped });
  }

  return sections;
}
