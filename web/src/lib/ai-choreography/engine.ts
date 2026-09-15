// Plays a script's steps at a human pace.
//
// Typing is ~18 ms per character, capped so a long line never takes more
// than 600 ms; `fast` (the server already answered) runs four times
// quicker; reduced motion makes every reveal instant and every pause a
// blink. Every wait is abortable between chunks, so Stop never leaves a
// half-typed value behind for more than one frame.

import { resolveAnchor } from "./anchors";
import type { ChoreographyContext, GhostVariant, Step, TypeTarget } from "./types";

export const MS_PER_CHAR = 18;
export const MAX_FIELD_MS = 600;
export const FAST_FACTOR = 4;

export interface RunOptions {
  signal: AbortSignal;
  /** Read on every chunk so a result arriving mid-step speeds it up. */
  isFast: () => boolean;
}

export class ChoreographyAborted extends Error {
  constructor() {
    super("choreography aborted");
    this.name = "ChoreographyAborted";
  }
}

function throwIfAborted(signal: AbortSignal): void {
  if (signal.aborted) throw new ChoreographyAborted();
}

/** Resolve after `ms`, or reject when the signal fires. */
export function sleep(ms: number, signal: AbortSignal): Promise<void> {
  throwIfAborted(signal);
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new ChoreographyAborted());
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

/** Poll until `probe` returns a value, up to `timeoutMs`. */
export async function waitUntil<T>(
  probe: () => T | null | undefined | false,
  timeoutMs: number,
  signal: AbortSignal,
): Promise<T | null> {
  const started = Date.now();
  for (;;) {
    const found = probe();
    if (found) return found;
    if (Date.now() - started >= timeoutMs) return null;
    await sleep(50, signal);
  }
}

/** How long the reveal of `value` takes at the current pace. */
export function revealDuration(value: string, ctx: ChoreographyContext, fast: boolean): number {
  if (ctx.reducedMotion) return 0;
  const natural = Math.min(MAX_FIELD_MS, value.length * MS_PER_CHAR);
  return fast ? natural / FAST_FACTOR : natural;
}

function applyValue(target: TypeTarget, value: unknown, ctx: ChoreographyContext): void {
  if (target.bridge === "page-editor") {
    if (target.field === "name") ctx.pageEditor.setName(String(value));
    else if (target.field === "line") ctx.pageEditor.setLine(target.index, String(value));
    else ctx.pageEditor.setDeviceType(String(value));
    return;
  }
  ctx.schedule.setField(target.field, value);
}

async function typeInto(target: TypeTarget, value: string, ctx: ChoreographyContext, opts: RunOptions): Promise<void> {
  const total = revealDuration(value, ctx, opts.isFast());
  if (total === 0 || value.length === 0) {
    applyValue(target, value, ctx);
    return;
  }
  // Reveal in chunks of a few characters so a long line still feels typed
  // without scheduling a timer per character.
  const chunks = Math.min(value.length, 24);
  const perChunk = Math.ceil(value.length / chunks);
  for (let shown = perChunk; shown < value.length; shown += perChunk) {
    applyValue(target, value.slice(0, shown), ctx);
    await sleep(revealDuration(value, ctx, opts.isFast()) / chunks, opts.signal);
  }
  applyValue(target, value, ctx);
}

async function ghostInto(
  anchor: string,
  value: string,
  variant: GhostVariant,
  ctx: ChoreographyContext,
  opts: RunOptions,
): Promise<void> {
  const total = variant === "badge" ? 0 : revealDuration(value, ctx, opts.isFast());
  if (total === 0) {
    ctx.spotlight.ghost(anchor, value, 1, variant);
    return;
  }
  const frames = Math.min(value.length, 24);
  for (let i = 1; i <= frames; i++) {
    ctx.spotlight.ghost(anchor, value, i / frames, variant);
    await sleep(revealDuration(value, ctx, opts.isFast()) / frames, opts.signal);
  }
}

/** Play `steps` in order. Throws ChoreographyAborted when the signal fires. */
export async function runSteps(steps: Step[], ctx: ChoreographyContext, opts: RunOptions): Promise<void> {
  for (const step of steps) {
    throwIfAborted(opts.signal);
    switch (step.kind) {
      case "navigate":
        if (ctx.pathname() !== step.href.split("?")[0] || step.href.includes("?")) ctx.navigate(step.href);
        // Give the router a frame to commit before anything waits on it.
        await sleep(ctx.reducedMotion ? 0 : 60, opts.signal);
        break;
      case "waitFor":
        await waitUntil(() => resolveAnchor(step.anchor), step.timeoutMs ?? 2500, opts.signal);
        break;
      case "waitBridge": {
        const ok =
          step.bridge === "page-editor"
            ? await ctx.pageEditor.waitFor(step.timeoutMs)
            : await ctx.schedule.waitForForm(step.timeoutMs);
        throwIfAborted(opts.signal);
        if (!ok) return; // the surface never came; the caption stays
        break;
      }
      case "spotlight":
        ctx.spotlight.show({ anchor: step.anchor, caption: step.caption, tone: step.tone, controls: step.controls });
        await sleep(ctx.reducedMotion ? 0 : opts.isFast() ? 120 : 350, opts.signal);
        break;
      case "caption":
        ctx.spotlight.caption(step.caption, step.tone);
        break;
      case "ghost":
        await ghostInto(step.anchor, step.value, step.variant ?? "replica", ctx, opts);
        break;
      case "type":
        await typeInto(step.target, step.value, ctx, opts);
        break;
      case "set":
        applyValue(step.target, step.value, ctx);
        break;
      case "pause":
        await sleep(
          ctx.reducedMotion ? Math.min(step.ms, 80) : opts.isFast() ? step.ms / FAST_FACTOR : step.ms,
          opts.signal,
        );
        break;
      case "pulse":
        ctx.spotlight.pulse(step.anchor);
        break;
      case "clearGhosts":
        ctx.spotlight.clearGhosts();
        break;
      case "hide":
        ctx.spotlight.hide();
        break;
      case "run":
        await step.run(ctx);
        break;
    }
  }
}
