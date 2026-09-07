import { createContext, useContext } from "react";

/**
 * Which plugin the surrounding {@link SchemaForm} is configuring.
 *
 * `SchemaForm` renders a manifest's settings schema without otherwise caring
 * whose manifest it is, but a `remote-options` field has to ask *that plugin*
 * for its catalog. `null` means the form was rendered without a plugin id — a
 * remote-options field then degrades to a disabled control rather than
 * throwing or firing a request at `/plugins/null/options/…`.
 */
export const SchemaFormPluginContext = createContext<string | null>(null);

export function usePluginId(): string | null {
  return useContext(SchemaFormPluginContext);
}

/**
 * Where a field sits in the value tree, so `ui:options.depends_on` can resolve
 * the sibling it names.
 *
 * `scope` is the object the field's own key lives in — the array *item* for a
 * field inside an array of objects, the sub-object for a nested object, the
 * whole config at the top level. `root` is always the whole config, so a
 * nested field may also depend on a top-level property.
 */
export interface FieldScope {
  scope: Record<string, unknown>;
  root: Record<string, unknown>;
  /**
   * Property name → display title at this level, so a field can name the
   * sibling it is waiting on ("Select Transit Agency first") instead of
   * leaking the raw schema key at the user.
   */
  titles: Record<string, string>;
}

export const FieldScopeContext = createContext<FieldScope>({ scope: {}, root: {}, titles: {} });

export function useFieldScope(): FieldScope {
  return useContext(FieldScopeContext);
}
