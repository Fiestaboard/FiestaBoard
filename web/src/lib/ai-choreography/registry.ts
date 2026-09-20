// Which walkthrough plays for which tool.
//
// Scripts are keyed by MCP tool name. A tool with no script of its own gets
// the generic one: go to the screen that owns it, point at the thing it
// touches, show the result land. That is why a new server tool still
// "shows its work" the day it ships — the script table is a refinement,
// never a gate.

import { fallbackScript } from "./scripts/fallback";
import { PAGE_SCRIPTS } from "./scripts/pages";
import { SCHEDULE_SCRIPTS } from "./scripts/schedules";
import { SETTINGS_SCRIPTS } from "./scripts/settings";
import type { ChoreographyScript } from "./types";

const SCRIPTS: Record<string, ChoreographyScript> = {
  ...PAGE_SCRIPTS,
  ...SCHEDULE_SCRIPTS,
  ...SETTINGS_SCRIPTS,
};

export function getScript(name: string): ChoreographyScript {
  return SCRIPTS[name] ?? fallbackScript;
}

/** Tools with their own script (the rest use the fallback). */
export function scriptedTools(): string[] {
  return Object.keys(SCRIPTS);
}

export { homeFor } from "./home";
