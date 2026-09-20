"use client";

import { Box, Button, GhostValue, SpotlightCaption, SpotlightRing, type SpotlightTone } from "@fiestaboard/ui";
import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useTranslations } from "@/i18n/translations";
import { resolveAnchor } from "@/lib/ai-choreography/anchors";
import type { GhostVariant, SpotlightApi, SpotlightControls } from "@/lib/ai-choreography/types";

/**
 * The spotlight: a ring around the control the assistant is acting on, a
 * caption saying what is happening (with Stop, or Approve/Deny), and ghost
 * values that show a setting arriving over its input before the real
 * value lands.
 *
 * Positions are measured from the anchor element every frame while
 * something is shown and written straight to the DOM through refs — never
 * through state — so scrolling, resizing and the 500 ms view transition
 * all keep the ring on its target without re-rendering the app.
 *
 * A frame is cheap by construction (#2041): it takes every measurement
 * before it writes any style, so however many ghosts are on screen the
 * browser is asked for at most one layout; the resolved anchor elements and
 * a replica's computed text metrics are held between frames rather than
 * queried again; and a frame in which nothing moved writes nothing at all.
 */

interface SpotlightState {
  anchor: string;
  caption: string;
  tone: SpotlightTone;
  controls: SpotlightControls;
}

interface GhostState {
  id: number;
  anchor: string;
  value: string;
  progress: number;
  variant: "replica" | "badge";
}

export interface SpotlightHandlers {
  onStop?: () => void;
  onApprove?: () => void;
  onDeny?: () => void;
}

interface SpotlightContextValue extends SpotlightApi {
  /** The drawer registers what Stop / Approve / Deny do. */
  setHandlers(handlers: SpotlightHandlers): void;
  /** True while a ring or caption is on screen. */
  active: boolean;
}

const SpotlightContext = createContext<SpotlightContextValue | null>(null);

const PULSE_CLASS = "ai-anchor-pulse";
const PULSE_MS = 1600;

/** Text inputs get a replica (the value typed in place); everything else a badge. */
function pickVariant(el: HTMLElement | null, requested: GhostVariant): "replica" | "badge" {
  if (requested !== "auto") return requested;
  if (!el) return "badge";
  const tag = el.tagName;
  if (tag === "TEXTAREA") return "replica";
  if (tag === "INPUT") {
    const type = (el as HTMLInputElement).type;
    return type === "checkbox" || type === "radio" || type === "range" ? "badge" : "replica";
  }
  const inner = el.querySelector<HTMLElement>(
    "input:not([type=checkbox]):not([type=radio]):not([type=range]), textarea",
  );
  return inner ? "replica" : "badge";
}

export function SpotlightProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<SpotlightState | null>(null);
  const [ghosts, setGhosts] = useState<GhostState[]>([]);
  const handlersRef = useRef<SpotlightHandlers>({});
  const ghostIdRef = useRef(0);

  const show = useCallback<SpotlightApi["show"]>(({ anchor, caption, tone = "driving", controls = "stop" }) => {
    setState({ anchor, caption, tone, controls });
    const el = resolveAnchor(anchor);
    if (el && typeof el.scrollIntoView === "function") {
      const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
    }
  }, []);

  const caption = useCallback<SpotlightApi["caption"]>((text, tone) => {
    setState((prev) => (prev ? { ...prev, caption: text, tone: tone ?? prev.tone } : prev));
  }, []);

  const hide = useCallback(() => setState(null), []);

  const pulse = useCallback((anchor: string) => {
    const el = resolveAnchor(anchor);
    if (!el) return;
    el.classList.add(PULSE_CLASS);
    window.setTimeout(() => el.classList.remove(PULSE_CLASS), PULSE_MS);
  }, []);

  const ghost = useCallback<SpotlightApi["ghost"]>((anchor, value, progress, requested) => {
    const variant = pickVariant(resolveAnchor(anchor), requested);
    setGhosts((prev) => {
      const existing = prev.find((g) => g.anchor === anchor);
      if (existing) return prev.map((g) => (g.anchor === anchor ? { ...g, value, progress, variant } : g));
      ghostIdRef.current += 1;
      return [...prev, { id: ghostIdRef.current, anchor, value, progress, variant }];
    });
  }, []);

  const clearGhosts = useCallback(() => setGhosts([]), []);

  const setHandlers = useCallback((handlers: SpotlightHandlers) => {
    handlersRef.current = handlers;
  }, []);

  const value = useMemo<SpotlightContextValue>(
    () => ({ show, caption, hide, pulse, ghost, clearGhosts, setHandlers, active: state !== null }),
    [show, caption, hide, pulse, ghost, clearGhosts, setHandlers, state],
  );

  return (
    <SpotlightContext.Provider value={value}>
      {children}
      <SpotlightOverlay state={state} ghosts={ghosts} handlersRef={handlersRef} />
    </SpotlightContext.Provider>
  );
}

export function useSpotlight(): SpotlightContextValue {
  const ctx = useContext(SpotlightContext);
  if (!ctx) throw new Error("useSpotlight must be used within SpotlightProvider");
  return ctx;
}

/**
 * The spotlight where there may not be a provider — the Toaster reads it to
 * keep out of the caption's way, and is also rendered on its own in
 * Storybook. Returns null rather than throwing.
 */
export function useOptionalSpotlight(): SpotlightContextValue | null {
  return useContext(SpotlightContext);
}

const RING_PAD = 6;

/**
 * How long a resolved anchor — or a replica's copied text metrics — is
 * trusted before being looked up again. An element that leaves the document
 * is re-resolved at once; this only bounds the slower kind of staleness (the
 * id now belongs to a different element, the theme changed the font under a
 * ghost) without paying for a DOM query and a style recalculation sixty
 * times a second.
 */
const REVALIDATE_MS = 250;

/** The text metrics a replica ghost copies from the input it sits over. */
interface ReplicaMetrics {
  font: string;
  paddingLeft: number;
}

/** One ghost, measured. Filled in the read pass, consumed in the write pass. */
interface GhostReading {
  node: HTMLElement;
  rect: DOMRect | null;
  metrics: ReplicaMetrics | null;
}

function SpotlightOverlay({
  state,
  ghosts,
  handlersRef,
}: {
  state: SpotlightState | null;
  ghosts: GhostState[];
  handlersRef: React.MutableRefObject<SpotlightHandlers>;
}) {
  const t = useTranslations("aiSpotlight");
  const ringRef = useRef<HTMLDivElement>(null);
  const captionRef = useRef<HTMLDivElement>(null);
  const ghostRefs = useRef(new Map<number, HTMLElement>());

  // The narration never moves focus. But the caption's own buttons can hold
  // it — Stop is the one the user is most likely to press — and the caption
  // then unmounts under them, which would drop focus to <body>. Give it
  // back to whatever had it before the user reached into the caption.
  const focusBeforeCaptionRef = useRef<HTMLElement | null>(null);
  const focusEnteredCaptionRef = useRef(false);
  const shown = state !== null;
  useLayoutEffect(() => {
    if (!shown) return;
    focusEnteredCaptionRef.current = false;
    focusBeforeCaptionRef.current = (document.activeElement as HTMLElement | null) ?? null;
    const caption = captionRef.current;
    const onFocusIn = () => {
      focusEnteredCaptionRef.current = true;
    };
    caption?.addEventListener("focusin", onFocusIn);
    return () => {
      caption?.removeEventListener("focusin", onFocusIn);
      // Only when the caption really held focus and losing it dropped focus
      // to the document — otherwise putting it back would be moving it.
      if (!focusEnteredCaptionRef.current) return;
      if (document.activeElement && document.activeElement !== document.body) return;
      const back = focusBeforeCaptionRef.current;
      if (back && back.isConnected) back.focus?.();
    };
  }, [shown]);

  // One measurement loop for the ring and every ghost, alive only while
  // something is shown. Writes go to the elements, not to React.
  //
  // Held between frames so a frame costs a browser as little as possible:
  // the element behind each anchor id, the computed text metrics of a
  // replica's target, and the last thing written to each node.
  const anchorCache = useRef(new Map<string, { el: HTMLElement; at: number }>());
  const metricsCache = useRef(new WeakMap<HTMLElement, { metrics: ReplicaMetrics; at: number }>());
  const writtenCache = useRef(new WeakMap<HTMLElement, string>());
  const readings = useRef<GhostReading[]>([]);

  // The ghost list is read through a ref so that typing a value — which
  // republishes it up to 24 times a field — does not tear the loop down and
  // rebuild its caches on every keystroke.
  const ghostsRef = useRef(ghosts);
  useLayoutEffect(() => {
    ghostsRef.current = ghosts;
  }, [ghosts]);

  const anchorId = state?.anchor ?? null;
  const running = anchorId !== null || ghosts.length > 0;
  useLayoutEffect(() => {
    if (!running) {
      anchorCache.current.clear();
      return;
    }

    const anchorFor = (id: string, now: number): HTMLElement | null => {
      const hit = anchorCache.current.get(id);
      if (hit && hit.el.isConnected && now - hit.at < REVALIDATE_MS) return hit.el;
      const el = resolveAnchor(id);
      if (el) anchorCache.current.set(id, { el, at: now });
      else anchorCache.current.delete(id);
      return el;
    };

    const metricsFor = (el: HTMLElement, now: number): ReplicaMetrics => {
      const hit = metricsCache.current.get(el);
      if (hit && now - hit.at < REVALIDATE_MS) return hit.metrics;
      const cs = window.getComputedStyle(el);
      const metrics = { font: cs.font, paddingLeft: parseFloat(cs.paddingLeft || "0") || 0 };
      metricsCache.current.set(el, { metrics, at: now });
      return metrics;
    };

    // A style write dirties layout, so the cheapest frame is the one that
    // writes nothing. `signature` is everything the write depends on.
    const write = (node: HTMLElement, signature: string, apply: (style: CSSStyleDeclaration) => void) => {
      if (writtenCache.current.get(node) === signature) return;
      writtenCache.current.set(node, signature);
      apply(node.style);
    };

    let frame = 0;
    const tick = (now: number) => {
      // Read pass: every measurement happens before any write, so the frame
      // asks the browser for one layout however many ghosts are on screen.
      const ring = ringRef.current;
      const ringEl = ring && anchorId ? anchorFor(anchorId, now) : null;
      const ringRect = ringEl ? ringEl.getBoundingClientRect() : null;

      const reads = readings.current;
      reads.length = 0;
      for (const g of ghostsRef.current) {
        const node = ghostRefs.current.get(g.id);
        if (!node) continue;
        const el = anchorFor(g.anchor, now);
        reads.push({
          node,
          rect: el ? el.getBoundingClientRect() : null,
          metrics: el && g.variant === "replica" ? metricsFor(el, now) : null,
        });
      }

      // Write pass.
      if (ring) {
        if (ringRect) {
          const x = ringRect.left - RING_PAD;
          const y = ringRect.top - RING_PAD;
          const w = ringRect.width + RING_PAD * 2;
          const h = ringRect.height + RING_PAD * 2;
          write(ring, `on:${x}:${y}:${w}:${h}`, (style) => {
            style.opacity = "1";
            style.transform = `translate(${x}px, ${y}px)`;
            style.width = `${w}px`;
            style.height = `${h}px`;
          });
        } else {
          write(ring, "off", (style) => {
            style.opacity = "0";
          });
        }
      }
      for (const { node, rect, metrics } of reads) {
        if (!rect) {
          write(node, "off", (style) => {
            style.opacity = "0";
          });
        } else if (metrics) {
          const x = rect.left + metrics.paddingLeft;
          write(node, `replica:${x}:${rect.top}:${rect.height}:${metrics.font}`, (style) => {
            style.opacity = "1";
            style.transform = `translate(${x}px, ${rect.top}px)`;
            style.height = `${rect.height}px`;
            style.font = metrics.font;
            style.lineHeight = `${rect.height}px`;
          });
        } else {
          write(node, `badge:${rect.right}:${rect.top}:${rect.height}`, (style) => {
            style.opacity = "1";
            style.transform = `translate(${rect.right + 8}px, ${rect.top + rect.height / 2}px) translateY(-50%)`;
          });
        }
      }

      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [running, anchorId]);

  if (typeof document === "undefined" || (!state && ghosts.length === 0)) return null;

  const controls =
    state?.controls === "approval" ? (
      <>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={() => handlersRef.current.onDeny?.()}
        >
          {t("deny")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="brand"
          className="h-7 text-xs"
          onClick={() => handlersRef.current.onApprove?.()}
        >
          {t("approve")}
        </Button>
      </>
    ) : state?.controls === "stop" ? (
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="h-7 text-xs"
        onClick={() => handlersRef.current.onStop?.()}
      >
        {t("stop")}
      </Button>
    ) : undefined;

  return createPortal(
    <Box data-ai-spotlight="" className="pointer-events-none fixed inset-0 z-[var(--z-spotlight)]" aria-hidden={false}>
      {state ? (
        <SpotlightRing
          ref={ringRef}
          tone={state.tone}
          data-testid="ai-spotlight-ring"
          data-anchor={state.anchor}
          className="fixed left-0 top-0 opacity-0 transition-[transform,width,height] duration-200 ease-out motion-reduce:transition-none"
        />
      ) : null}
      {ghosts.map((g) => (
        <Box
          key={g.id}
          ref={(node: HTMLElement | null) => {
            if (node) ghostRefs.current.set(g.id, node);
            else ghostRefs.current.delete(g.id);
          }}
          aria-hidden="true"
          data-testid="ai-ghost"
          data-anchor={g.anchor}
          className="fixed left-0 top-0 flex items-center opacity-0"
        >
          {/* `relative` keeps the value in flow so the box it is measured
              against has the value's own size; the primitive is `absolute`. */}
          <GhostValue className="relative" value={g.value} progress={g.progress} variant={g.variant} />
        </Box>
      ))}
      {state ? (
        // The caption positions itself: it is the primitive that carries
        // `role="status"`, so wrapping it in a second live region would
        // announce every change twice — and an `absolute` child inside a
        // shrink-to-fit wrapper leaves the wrapper with no box at all.
        <SpotlightCaption
          ref={captionRef}
          tone={state.tone}
          controls={controls}
          data-testid="ai-spotlight-caption"
          className="pointer-events-auto fixed bottom-6 left-1/2 z-10 -translate-x-1/2"
        >
          {state.caption}
        </SpotlightCaption>
      ) : null}
    </Box>,
    document.body,
  );
}
