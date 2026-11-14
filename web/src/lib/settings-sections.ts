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
 * landing in the right place. General was split across You and Hub; a bare
 * link to it lands on Appearance, the first of its cards.
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
 * Where an old `?section=` link goes now, or `null` when it names no
 * settings section (the Displays redirects handle `hardware`, `scheduling`
 * and `behavior` themselves).
 */
export function legacySettingsTarget(section: string | null): SettingsSectionId | null {
  if (section === null) return null;
  return Object.hasOwn(LEGACY_SECTIONS, section) ? LEGACY_SECTIONS[section] : null;
}

/**
 * The section a request shows. An unknown or hidden section falls back to the
 * first visible one: a list-detail always has something in its detail pane.
 */
export function resolveSettingsSection(
  requested: string | undefined,
  visible: readonly SettingsSectionId[],
): SettingsSectionId {
  if (isSettingsSectionId(requested) && visible.includes(requested)) return requested;
  return visible[0] ?? "appearance";
}
