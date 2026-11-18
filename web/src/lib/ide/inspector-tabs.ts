import type { DataSource } from "@fiestaboard/ui";

/** The Creator IDE Inspector tabs (04d), in drawn order. */
export type IdeTabId = "data" | "logic" | "page" | "shows-on" | "problems" | "history";

/** At and above this width the IDE docks Problems in the console (Jev desktop_console_two_option). */
export const IDE_DESKTOP_QUERY = "(min-width: 1024px)";

const DESKTOP_TABS: readonly IdeTabId[] = ["data", "logic", "page", "shows-on", "history"];
const COMPACT_TABS: readonly IdeTabId[] = ["data", "logic", "page", "shows-on", "problems", "history"];

/**
 * Desktop (>= 1024 px) draws five tabs with Problems docked in the console
 * beside Sent; narrower widths add Problems back as the sixth tab.
 */
export function inspectorTabIds(desktop: boolean): readonly IdeTabId[] {
  return desktop ? DESKTOP_TABS : COMPACT_TABS;
}

/** A tab that no longer exists after a breakpoint change falls back to Page (the drawn default). */
export function resolveInspectorTab(current: IdeTabId, desktop: boolean): IdeTabId {
  return inspectorTabIds(desktop).includes(current) ? current : "page";
}

/** The preview data switch: Live and Sample on desktop as drawn; Missing returns below 1024 px. */
export function ideDataSources(desktop: boolean): readonly DataSource[] {
  return desktop ? ["live", "sample"] : ["live", "sample", "missing"];
}

export function isIdeTabId(value: unknown): value is IdeTabId {
  return typeof value === "string" && (COMPACT_TABS as readonly string[]).includes(value);
}
