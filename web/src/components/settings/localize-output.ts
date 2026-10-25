/**
 * Translations for an output's board settings screen (plan D13).
 *
 * A manifest's text — field titles, descriptions and placeholders, mode
 * cards, sections, action labels and their input fields — is English. When
 * the app's messages carry `outputSettings.<output id>.…` for a piece of it,
 * the screen shows that instead, in the user's language (English is the
 * per-key fallback). It is data the app ships, never plugin code: today the
 * first-party outputs' screens are translated this way, so moving the
 * Vestaboard's form onto the renderer did not cost its 13 translations.
 *
 *     outputSettings.<output>.fields.<name>.{title, description, placeholder}
 *     outputSettings.<output>.fields.<name>.cards.<value>.{title, description}
 *     outputSettings.<output>.fields.<name>.items.<name>.{title, description, placeholder}
 *     outputSettings.<output>.sections.<id>.{title, description}
 *     outputSettings.<output>.actions.<id>.{label, description}
 *     outputSettings.<output>.actions.<id>.input.<name>.{title, description, placeholder}
 */
import type { OutputActionDescriptor, OutputSummary } from "@/lib/api";

/** Looks up one message by its key under `outputSettings`; `undefined` when there is none. */
export type OutputText = (key: string) => string | undefined;

type Json = Record<string, unknown>;

function isObject(value: unknown): value is Json {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function localizeProperty(prop: Json, prefix: string, text: OutputText): Json {
  const out: Json = { ...prop };
  const title = text(`${prefix}.title`);
  const description = text(`${prefix}.description`);
  const placeholder = text(`${prefix}.placeholder`);
  if (title !== undefined) out.title = title;
  if (description !== undefined) out.description = description;
  if (placeholder !== undefined) out["ui:placeholder"] = placeholder;
  const options = prop["ui:options"];
  if (isObject(options) && Array.isArray(options.cards)) {
    out["ui:options"] = {
      ...options,
      cards: options.cards.map((card) => {
        if (!isObject(card)) return card;
        const at = `${prefix}.cards.${String(card.value)}`;
        return {
          ...card,
          ...(text(`${at}.title`) !== undefined ? { title: text(`${at}.title`) } : {}),
          ...(text(`${at}.description`) !== undefined ? { description: text(`${at}.description`) } : {}),
        };
      }),
    };
  }
  if (isObject(prop.items) && isObject(prop.items.properties)) {
    out.items = { ...prop.items, properties: localizeProperties(prop.items.properties, `${prefix}.items`, text) };
  }
  if (isObject(prop.properties)) out.properties = localizeProperties(prop.properties, prefix, text);
  return out;
}

function localizeProperties(props: Json, prefix: string, text: OutputText): Json {
  return Object.fromEntries(
    Object.entries(props).map(([name, prop]) => [
      name,
      isObject(prop) ? localizeProperty(prop, `${prefix}.${name}`, text) : prop,
    ]),
  );
}

function localizeSchema(schema: Json | null | undefined, prefix: string, text: OutputText): Json | null {
  if (!isObject(schema)) return schema ?? null;
  const out: Json = { ...schema };
  if (isObject(schema.properties)) out.properties = localizeProperties(schema.properties, prefix, text);
  if (Array.isArray(schema["ui:sections"])) {
    out["ui:sections"] = schema["ui:sections"].map((section) => {
      if (!isObject(section)) return section;
      const at = `sections.${String(section.id)}`;
      return {
        ...section,
        ...(text(`${at}.title`) !== undefined ? { title: text(`${at}.title`) } : {}),
        ...(text(`${at}.description`) !== undefined ? { description: text(`${at}.description`) } : {}),
      };
    });
  }
  return out;
}

function localizeAction(action: OutputActionDescriptor, text: OutputText): OutputActionDescriptor {
  const at = `actions.${action.id}`;
  return {
    ...action,
    label: text(`${at}.label`) ?? action.label,
    description: text(`${at}.description`) ?? action.description,
    input_schema: localizeSchema(action.input_schema, `${at}.input`, text),
  };
}

/** *output* with its settings screen's text in the user's language, where the app carries it. */
export function localizeOutput(output: OutputSummary, text: OutputText): OutputSummary {
  const scoped: OutputText = (key) => text(`${output.id}.${key}`);
  return {
    ...output,
    settings_schema: localizeSchema(output.settings_schema, "fields", scoped) ?? {},
    actions: output.actions.map((action) => localizeAction(action, scoped)),
  };
}
