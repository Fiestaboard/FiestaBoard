import { Accessibility, Palette, User } from "lucide-react";

import { HUB_SETTINGS_LINKS, type HubSettingsLink } from "@/lib/nav-items";

/**
 * Settings as a list-detail (slice 2.1, WEB-01; Figma 07e §1 `318:46000`,
 * `320:7936`, `320:6520`): the reader's own settings ("You"), then the hub's
 * ("Hub · <name>", the Settings › Hub group the More sheet also lists). Each
 * section is a route, `/settings/:section`.
 *
 * Notifications (WEB-13) and FiestaBot behaviour arrive with slices 2.13 and
 * 2.14; their rows join the You group then.
 */

export type HubSettingsSectionId = HubSettingsLink["section"];
export type YouSettingsSectionId = "account" | "appearance" | "accessibility";
export type SettingsSectionId = YouSettingsSectionId | HubSettingsSectionId;
export type SettingsGroup = "you" | "hub";

export interface SettingsSectionDef {
  id: SettingsSectionId;
  group: SettingsGroup;
  icon: React.ComponentType<{ className?: string }>;
}

export const SETTINGS_SECTIONS: readonly SettingsSectionDef[] = [
  { id: "account", group: "you", icon: User },
  { id: "appearance", group: "you", icon: Palette },
  { id: "accessibility", group: "you", icon: Accessibility },
  ...HUB_SETTINGS_LINKS.map((link) => ({ id: link.section, group: "hub" as const, icon: link.icon })),
];

export function isSettingsSectionId(value: string | null | undefined): value is SettingsSectionId {
  return SETTINGS_SECTIONS.some((section) => section.id === value);
}

/** The `/settings/:section` path for a section. */
export function settingsSectionHref(id: SettingsSectionId): string {
  return `/settings/${id}`;
}

/**
 * The six tabs `/settings?section=` used to name, mapped to the section that
 * now holds their cards, so bookmarks, docs links and the OAuth return keep
 * landing in the right place.
 *
 * Load-bearing: the hub's OAuth return (`src/oauth/routes.py`) still sends
 * the browser to `settings?section=ai&oauth=…`. Keep `ai` here (with its query
 * parameters carried through) until the server emits `/settings/ai-provider`.
 */
export const LEGACY_SECTIONS: Readonly<Record<string, SettingsSectionId>> = {
  general: "appearance",
  account: "account",
  network: "network",
  ai: "ai-provider",
  integrations: "ai-provider",
  system: "system",
  advanced: "system",
};

/**
 * General was split across You and Hub, so an anchored General link goes
 * where its card went. Unlisted anchors (and a bare link) land on Appearance,
 * the first of its cards.
 */
export const LEGACY_GENERAL_ANCHORS: Readonly<Record<string, SettingsSectionId>> = {
  location: "language-time",
  language: "language-time",
  time: "language-time",
  "time-and-date": "language-time",
  timezone: "language-time",
  mqtt: "network",
  "instance-name": "system",
  general: "system",
};

/**
 * Where an old `?section=` link goes now, or `null` when it names no
 * settings section (the Displays redirects handle `hardware`, `scheduling`
 * and `behavior` themselves). `hash` is the link's `#card` anchor, with or
 * without the `#`.
 */
export function legacySettingsTarget(section: string | null, hash = ""): SettingsSectionId | null {
  if (section === null || !Object.hasOwn(LEGACY_SECTIONS, section)) return null;
  const anchor = hash.replace(/^#/, "");
  if (section === "general" && Object.hasOwn(LEGACY_GENERAL_ANCHORS, anchor)) {
    return LEGACY_GENERAL_ANCHORS[anchor];
  }
  return LEGACY_SECTIONS[section];
}

/**
 * The section a request shows, or `null` when `requested` names no section
 * the reader can see (the route sends that to the index). No section named
 * means the first visible one: a list-detail always has something open.
 */
export function resolveSettingsSection(
  requested: string | undefined,
  visible: readonly SettingsSectionId[],
): SettingsSectionId | null {
  if (requested === undefined) return visible[0] ?? "appearance";
  if (isSettingsSectionId(requested) && visible.includes(requested)) return requested;
  return null;
}
