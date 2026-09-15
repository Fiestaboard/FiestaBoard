"use client";

import { Box, Button, GhostValue, SpotlightCaption, SpotlightRing, type SpotlightTone } from "@fiestaboard/ui";
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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

const RING_PAD = 6;

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
  const ghostRefs = useRef(new Map<number, HTMLElement>());
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // One measurement loop for the ring and every ghost, alive only while
  // something is shown. Writes go to the elements, not to React.
  const anchorId = state?.anchor ?? null;
  useLayoutEffect(() => {
    if (!anchorId && ghosts.length === 0) return;
    let frame = 0;
    const tick = () => {
      const ring = ringRef.current;
      if (ring && anchorId) {
        const el = resolveAnchor(anchorId);
        if (el) {
          const r = el.getBoundingClientRect();
          ring.style.opacity = "1";
          ring.style.transform = `translate(${r.left - RING_PAD}px, ${r.top - RING_PAD}px)`;
          ring.style.width = `${r.width + RING_PAD * 2}px`;
          ring.style.height = `${r.height + RING_PAD * 2}px`;
        } else {
          ring.style.opacity = "0";
        }
      }
      for (const g of ghosts) {
        const node = ghostRefs.current.get(g.id);
        const el = resolveAnchor(g.anchor);
        if (!node) continue;
        if (!el) {
          node.style.opacity = "0";
          continue;
        }
        const r = el.getBoundingClientRect();
        node.style.opacity = "1";
        if (g.variant === "replica") {
          const cs = window.getComputedStyle(el);
          node.style.transform = `translate(${r.left + parseFloat(cs.paddingLeft || "0")}px, ${r.top}px)`;
          node.style.height = `${r.height}px`;
          node.style.font = cs.font;
          node.style.lineHeight = `${r.height}px`;
        } else {
          node.style.transform = `translate(${r.right + 8}px, ${r.top + r.height / 2}px) translateY(-50%)`;
        }
      }
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [anchorId, ghosts]);

  if (!mounted || (!state && ghosts.length === 0)) return null;

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
    <Box data-ai-spotlight="" className="pointer-events-none fixed inset-0 z-[60]" aria-hidden={false}>
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
          <GhostValue value={g.value} progress={g.progress} variant={g.variant} />
        </Box>
      ))}
      {state ? (
        <Box
          role="status"
          aria-live="polite"
          className="pointer-events-auto fixed bottom-6 left-1/2 z-[61] -translate-x-1/2"
          data-testid="ai-spotlight-caption"
        >
          <SpotlightCaption tone={state.tone} controls={controls}>
            {state.caption}
          </SpotlightCaption>
        </Box>
      ) : null}
    </Box>,
    document.body,
  );
}
