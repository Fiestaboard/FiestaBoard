/** The Inspector Page tab's settings (UX-7-1): page content, staged until Save. */
export interface PageSettings {
  duration_seconds?: number | null;
  transition_strategy?: string | null;
}

export type PageSettingKey = "duration" | "transition";

/** Which Page-tab settings the editor changed against the saved page, for the discard list. */
export function changedPageSettings(
  current: PageSettings | null | undefined,
  saved: PageSettings | null | undefined,
): PageSettingKey[] {
  if (!current || !saved) return [];
  const changed: PageSettingKey[] = [];
  if (current.duration_seconds != null && current.duration_seconds !== saved.duration_seconds) changed.push("duration");
  if ((current.transition_strategy ?? null) !== (saved.transition_strategy ?? null)) changed.push("transition");
  return changed;
}
