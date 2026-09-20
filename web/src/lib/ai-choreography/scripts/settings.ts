// Settings: every value is ghost-typed over its control, then the card
// pulses once the real value has landed. No per-card bridge: the ghost is
// a DOM-level overlay, so all thirty-odd settings cards get the reveal for
// free — a control that has no anchor of its own falls back to its card.

import type { UpdateSettingArgs } from "@/lib/ai-chat-types";

import { settingAnchors, settingsHref } from "../anchors";
import type { ChoreographyScript, Step } from "../types";
import { failed, landed } from "./fallback";

/** How a value reads in a ghost. */
export function formatSettingValue(value: unknown, t: (key: string) => string): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? t("on") : t("off");
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

const updateSetting: ChoreographyScript = {
  narrate(call, ctx) {
    const a = call.args as unknown as UpdateSettingArgs;
    const values = a.values ?? {};
    const keys = Object.keys(values);
    const first = keys[0] ? settingAnchors(a.category, keys[0]) : undefined;
    const cardAnchor = first?.card ?? `settings.${a.category}`;
    const steps: Step[] = [
      { kind: "navigate", href: settingsHref(a.category) },
      { kind: "waitFor", anchor: first?.control ?? cardAnchor, timeoutMs: 2500 },
      {
        kind: "spotlight",
        anchor: cardAnchor,
        caption: ctx.t("changingSetting", { tool: ctx.label(call) }),
        controls: "stop",
      },
    ];
    for (const key of keys) {
      // The control's anchor, always: `resolveAnchor` falls back to the
      // card at play time, which is the only time the tab is on screen.
      const anchor = settingAnchors(a.category, key).control;
      steps.push({
        kind: "spotlight",
        anchor,
        caption: ctx.t("changingSetting", { tool: ctx.label(call) }),
        controls: "stop",
      });
      steps.push({ kind: "ghost", anchor, value: formatSettingValue(values[key], ctx.t), variant: "auto" });
      steps.push({ kind: "pause", ms: 280 });
    }
    return steps;
  },
  settle(call, _result, ctx) {
    const a = call.args as unknown as UpdateSettingArgs;
    const keys = Object.keys(a.values ?? {});
    const anchor = keys[0] ? settingAnchors(a.category, keys[0]).card : `settings.${a.category}`;
    // Keep the ghosts a beat so the real value's arrival reads as the same
    // thing landing, then let the pulse take over.
    return [{ kind: "pause", ms: 500 }, ...landed(anchor, ctx.t("settingSaved"))];
  },
  fail(_call, result, ctx) {
    return failed(result.error ?? ctx.t("settingFailed"));
  },
  stop() {
    return [{ kind: "clearGhosts" }, { kind: "hide" }];
  },
};

export const SETTINGS_SCRIPTS: Record<string, ChoreographyScript> = {
  update_setting: updateSetting,
};
