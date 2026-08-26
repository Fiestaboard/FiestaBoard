"use client";

import type { Code62Glyph } from "@fiestaboard/ui";
import { useEffect, useRef, useState } from "react";

import { PanelBoard } from "@/components/panel/panel-board";
import { usePanelConfig, usePanelFrame } from "@/hooks/use-panel";
import { useTranslations } from "@/i18n/translations";

interface PanelViewProps {
  panelId: string;
  /** Poll cadence overrides (tests use fast values). */
  frameIntervalMs?: number;
  configIntervalMs?: number;
}

const NOT_FOUND_DETAIL = "Panel not found";

/** Idle time before the cursor hides on the TV. */
const CURSOR_HIDE_MS = 3_000;

/** How often the auto-dim window is re-evaluated. */
const DIM_TICK_MS = 30_000;

/**
 * Whether `minutesSinceMidnight` falls inside the [start, end) dim window.
 * `start > end` means the window spans midnight (e.g. 22:00 → 07:00).
 * `start === end` never dims.
 */
export function isInDimWindow(minutesSinceMidnight: number, start: string, end: string): boolean {
  const toMinutes = (hhmm: string) => {
    const [h, m] = hhmm.split(":").map(Number);
    return h * 60 + m;
  };
  const startMin = toMinutes(start);
  const endMin = toMinutes(end);
  if (startMin === endMin) return false;
  if (startMin < endMin) return minutesSinceMidnight >= startMin && minutesSinceMidnight < endMin;
  return minutesSinceMidnight >= startMin || minutesSinceMidnight < endMin;
}

const BACKDROPS: Record<"wall" | "dark" | "none", React.CSSProperties> = {
  // A softly lit wall: key light falling from above, near-black at the edges.
  wall: {
    background: "radial-gradient(ellipse 120% 85% at 50% -15%, #2b2723 0%, #1c1a17 48%, #121110 100%)",
  },
  dark: { background: "#0a0a0a" },
  none: { background: "#000000" },
};

/**
 * Full-viewport FiestaPanel scene: the board at physical scale in a
 * room-like setting, polling its virtual board for frames.
 */
export function PanelView({ panelId, frameIntervalMs, configIntervalMs }: PanelViewProps) {
  const t = useTranslations("fiestaPanels");
  const config = usePanelConfig(panelId, configIntervalMs);
  const frame = usePanelFrame(panelId, frameIntervalMs);

  const [cursorHidden, setCursorHidden] = useState(false);
  const [dimActive, setDimActive] = useState(false);
  const cursorTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const notFound =
    (config.error instanceof Error && config.error.message === NOT_FOUND_DETAIL) ||
    (frame.error instanceof Error && frame.error.message === NOT_FOUND_DETAIL && !config.data);
  const offline = !notFound && !!(config.data || frame.data) && (config.isError || frame.isError);

  const autoDim = config.data?.auto_dim;

  // Keep the TV awake while the panel is showing (best effort).
  useEffect(() => {
    let sentinel: { release: () => Promise<void> } | null = null;
    let disposed = false;

    const acquire = async () => {
      try {
        const lock = await navigator.wakeLock?.request("screen");
        if (lock) {
          if (disposed) await lock.release();
          else sentinel = lock;
        }
      } catch {
        // Not supported or denied — the user's TV sleep settings rule.
      }
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") void acquire();
    };

    void acquire();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      disposed = true;
      document.removeEventListener("visibilitychange", onVisibility);
      void sentinel?.release();
    };
  }, []);

  // Hide the cursor after a few idle seconds.
  useEffect(() => {
    const wake = () => {
      setCursorHidden(false);
      if (cursorTimer.current) clearTimeout(cursorTimer.current);
      cursorTimer.current = setTimeout(() => setCursorHidden(true), CURSOR_HIDE_MS);
    };
    wake();
    window.addEventListener("mousemove", wake);
    return () => {
      window.removeEventListener("mousemove", wake);
      if (cursorTimer.current) clearTimeout(cursorTimer.current);
    };
  }, []);

  // Evaluate the auto-dim window against the TV's local clock.
  useEffect(() => {
    if (!autoDim?.enabled) {
      setDimActive(false);
      return;
    }
    const tick = () => {
      const now = new Date();
      setDimActive(isInDimWindow(now.getHours() * 60 + now.getMinutes(), autoDim.start, autoDim.end));
    };
    tick();
    const interval = setInterval(tick, DIM_TICK_MS);
    return () => clearInterval(interval);
  }, [autoDim?.enabled, autoDim?.start, autoDim?.end]);

  const toggleFullscreen = () => {
    try {
      if (document.fullscreenElement) void document.exitFullscreen();
      else void document.documentElement.requestFullscreen?.();
    } catch {
      // Some TV browsers refuse; they're usually fullscreen already.
    }
  };

  const backdrop = BACKDROPS[config.data?.backdrop ?? "dark"];

  let content: React.ReactNode;
  if (notFound) {
    content = (
      <div className="text-center text-neutral-400">
        <p className="text-2xl font-medium">{t("notFoundTitle")}</p>
        <p className="mt-2 text-base text-neutral-500">{t("notFoundBody")}</p>
      </div>
    );
  } else if (config.data?.board_missing) {
    content = (
      <div className="text-center text-neutral-400">
        <p className="text-2xl font-medium">{t("boardMissingTitle")}</p>
        <p className="mt-2 text-base text-neutral-500">{t("boardMissingBody")}</p>
      </div>
    );
  } else if (config.data) {
    content = (
      <PanelBoard
        message={frame.data?.message ?? null}
        deviceType={config.data.device_type === "note" ? "note" : "flagship"}
        boardColor={config.data.board_color ?? "black"}
        code62Glyph={(config.data.code62_glyph ?? "degree") as Code62Glyph}
        diagonalInches={config.data.screen_diagonal_inches}
        calibration={config.data.calibration_scale}
      />
    );
  } else {
    // Still connecting: a dark, quiet screen — the board arrives with data.
    content = null;
  }

  return (
    <div
      data-testid="panel-scene"
      data-panel-id={panelId}
      className="fixed inset-0 flex items-center justify-center overflow-hidden"
      style={{ ...backdrop, cursor: cursorHidden ? "none" : undefined }}
      onClick={toggleFullscreen}
    >
      {content}
      {/* Edge vignette (wall backdrop only) so the letterboxed area reads
          as a lit room instead of dead pixels. */}
      {config.data?.backdrop === "wall" && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{ boxShadow: "inset 0 0 18vmin rgba(0,0,0,0.65)" }}
        />
      )}
      {/* Auto-dim: slow-fading brightness overlay during the night window. */}
      <div
        aria-hidden="true"
        data-testid="panel-dim"
        data-active={dimActive ? "true" : "false"}
        className="pointer-events-none absolute inset-0 bg-black"
        style={{ opacity: dimActive ? 0.65 : 0, transition: "opacity 5s ease" }}
      />
      {offline && (
        <div
          data-testid="panel-offline"
          title={t("offline")}
          className="absolute right-4 bottom-4 size-2 rounded-full bg-amber-500/60"
        >
          <span className="sr-only">{t("offline")}</span>
        </div>
      )}
    </div>
  );
}
