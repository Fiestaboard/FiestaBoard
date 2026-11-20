import { ApiError } from "@/lib/api/core";

/**
 * The per-field messages of a rejected plugin config, or null when the
 * failure was something else. The hub answers a config that fails the
 * manifest's rules with `detail: {message, errors: string[]}`
 * (`src/plugins/routes.py`, PluginConfigInvalid).
 */
export function pluginConfigErrors(error: unknown): string[] | null {
  if (!(error instanceof ApiError)) return null;
  const detail = error.detail as { errors?: unknown } | undefined;
  if (!detail || typeof detail !== "object" || !Array.isArray(detail.errors)) return null;
  const messages = detail.errors.filter((message): message is string => typeof message === "string" && !!message);
  return messages.length > 0 ? messages : null;
}

export interface MappedConfigErrors {
  /** Messages each pinned to the settings field they are about. */
  fields: Record<string, string[]>;
  /** Messages that name no field the form shows. */
  general: string[];
}

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** A field's title as messages spell it: "Refresh Interval (seconds)" → "refresh interval". */
const titleStem = (title: string) =>
  title
    .replace(/\([^)]*\)/g, "")
    .trim()
    .toLowerCase();

/**
 * Pin the hub's free-text validation messages to settings fields. Plugins
 * write these messages by hand, so a message is matched to a field when it
 * names the field's key ("choices[2] must be…") or starts with or contains
 * its title ("Refresh interval must be at least 60 seconds"). The longest
 * match wins, so "API Key …" goes to `api_key` and not to a field titled
 * "API". Duplicates (the base class and a plugin can both check the refresh
 * interval) are reported once.
 */
export function mapConfigErrors(
  messages: string[],
  properties: Record<string, { title?: string }>,
): MappedConfigErrors {
  const fields: Record<string, string[]> = {};
  const general: string[] = [];
  for (const message of new Set(messages)) {
    const lower = message.toLowerCase();
    let best: { key: string; length: number } | null = null;
    for (const [key, property] of Object.entries(properties)) {
      const candidates = [key.toLowerCase(), property.title ? titleStem(property.title) : ""];
      for (const candidate of candidates) {
        if (!candidate) continue;
        if (!new RegExp(`(^|[^a-z0-9_])${escape(candidate)}($|[^a-z0-9_])`).test(lower)) continue;
        if (!best || candidate.length > best.length) best = { key, length: candidate.length };
      }
    }
    if (best) (fields[best.key] ??= []).push(message);
    else general.push(message);
  }
  return { fields, general };
}
