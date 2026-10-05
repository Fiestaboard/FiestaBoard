/**
 * `ui:visible_when` — the one condition grammar of the board settings
 * contract (plan D13), evaluated here and in Python validation
 * (`src/plugins/settings_ui.py`) identically. Both sides run the vectors in
 * `./visible-when.cases.json`; change one side and the other's test fails.
 *
 *     Condition := { "<field>": <scalar> }          field equals the scalar
 *                | { "<field>": [<scalar>, ...] }   field is one of them
 *                | { "<f1>": ..., "<f2>": ... }     every pair holds (AND)
 *                | { "not": Condition }             negation ("not" alone)
 *                | { "any": [Condition, ...] }      at least one holds ("any" alone)
 *
 * Scalars are compared as JSON with no coercion (`true` is not `1`). A field
 * absent from the values reads as its schema `default`, else `null`. A
 * malformed condition evaluates to visible — a typo never hides a field (and
 * the manifest validator refuses it, so it never ships).
 */

type Scalar = string | number | boolean | null;

function isScalar(value: unknown): value is Scalar {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}

function jsonEqual(actual: unknown, expected: Scalar): boolean {
  if (!isScalar(actual)) return false;
  return typeof actual === typeof expected && actual === expected;
}

function valueOf(field: string, values: Record<string, unknown>, properties: Record<string, unknown>): unknown {
  if (Object.prototype.hasOwnProperty.call(values, field)) return values[field];
  const prop = properties[field];
  if (prop && typeof prop === "object" && "default" in prop) {
    return (prop as { default?: unknown }).default ?? null;
  }
  return null;
}

/** `true`/`false`, or `null` when the condition is malformed. */
function evaluate(cond: unknown, values: Record<string, unknown>, properties: Record<string, unknown>): boolean | null {
  if (!cond || typeof cond !== "object" || Array.isArray(cond)) return null;
  const entries = Object.entries(cond as Record<string, unknown>);
  if (entries.length === 0) return null;
  const record = cond as Record<string, unknown>;
  if ("not" in record || "any" in record) {
    if (entries.length !== 1) return null;
    if ("not" in record) {
      const inner = evaluate(record.not, values, properties);
      return inner === null ? null : !inner;
    }
    const branches = record.any;
    if (!Array.isArray(branches) || branches.length === 0) return null;
    const results = branches.map((branch) => evaluate(branch, values, properties));
    if (results.some((r) => r === null)) return null;
    return results.some(Boolean);
  }
  for (const [field, expected] of entries) {
    const actual = valueOf(field, values, properties);
    if (Array.isArray(expected)) {
      if (!expected.every(isScalar)) return null;
      if (!expected.some((e) => jsonEqual(actual, e))) return false;
    } else if (isScalar(expected)) {
      if (!jsonEqual(actual, expected)) return false;
    } else {
      return null;
    }
  }
  return true;
}

/**
 * Whether a field with `ui:visible_when` *cond* shows, given the values of the
 * object it lives in and that object's property schemas (for defaults).
 */
export function isVisible(
  cond: unknown,
  values: Record<string, unknown> | null | undefined,
  properties?: Record<string, unknown> | null,
): boolean {
  if (cond === undefined) return true;
  const result = evaluate(cond, values ?? {}, properties ?? {});
  return result === null ? true : result;
}
