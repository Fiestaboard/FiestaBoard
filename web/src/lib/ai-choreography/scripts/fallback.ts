// The walkthrough every tool gets unless it has a better one.

import { homeFor } from "../home";
import type { ChoreographyScript, Step } from "../types";

export const fallbackScript: ChoreographyScript = {
  narrate(call, ctx) {
    if (call.read_only) return [];
    const { href, anchor } = homeFor(call);
    return [
      { kind: "navigate", href },
      { kind: "waitFor", anchor, timeoutMs: 1500 },
      { kind: "spotlight", anchor, caption: ctx.t("working", { tool: ctx.label(call) }), controls: "stop" },
    ];
  },
  settle(call, _result, ctx) {
    if (call.read_only) return [];
    const { anchor } = homeFor(call);
    return landed(anchor, ctx.t("done", { tool: ctx.label(call) }));
  },
  fail(call, result, ctx) {
    if (call.read_only) return [];
    return failed(result.error ?? ctx.t("failed", { tool: ctx.label(call) }));
  },
  stop() {
    return [{ kind: "clearGhosts" }, { kind: "hide" }];
  },
  approvalAnchor(call) {
    return homeFor(call).anchor;
  },
};

/** The shared ending: the landed ring, a beat, then out of the way. */
export function landed(anchor: string, caption: string): Step[] {
  return [
    { kind: "clearGhosts" },
    { kind: "caption", caption, tone: "landed" },
    { kind: "pulse", anchor },
    { kind: "pause", ms: 1100 },
    { kind: "hide" },
  ];
}

export function failed(caption: string): Step[] {
  return [
    { kind: "clearGhosts" },
    { kind: "caption", caption, tone: "error" },
    { kind: "pause", ms: 1800 },
    { kind: "hide" },
  ];
}
