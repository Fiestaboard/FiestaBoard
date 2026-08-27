"use client";

import { Box, type Code62Glyph, Flex, Text } from "@fiestaboard/ui";
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

/**
 * Full-viewport FiestaPanel scene: a borderless auto-fit grid at true flap
 * scale on pure black, polling its virtual board for frames.
 */
export function PanelView({ panelId, frameIntervalMs, configIntervalMs }: PanelViewProps) {
  const t = useTranslations("fiestaPanels");
  const config = usePanelConfig(panelId, configIntervalMs);
  const frame = usePanelFrame(panelId, frameIntervalMs);

  const [cursorHidden, setCursorHidden] = useState(false);
  // The TV's clock, in minutes since midnight; ticked by an interval so the
  // dim window is derived at render instead of set inside an effect body.
  const [minutesNow, setMinutesNow] = useState(() => {
    const now = new Date();
    return now.getHours() * 60 + now.getMinutes();
  });
  const cursorTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const notFound =
    (config.error instanceof Error && config.error.message === NOT_FOUND_DETAIL) ||
    (frame.error instanceof Error && frame.error.message === NOT_FOUND_DETAIL && !config.data);
  const offline = !notFound && !!(config.data || frame.data) && (config.isError || frame.isError);

  const autoDim = config.data?.auto_dim;

  // Panel mode: pin the page itself — no scrollbars, black behind
  // everything (globals.css .panel-mode rules on html/body). The scene div
  // is fixed inset-0, but an oversized true-scale board must never let the
  // document scroll or reveal a non-black backdrop behind it.
  useEffect(() => {
    document.documentElement.classList.add("panel-mode");
    return () => document.documentElement.classList.remove("panel-mode");
  }, []);

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

  // Keep the clock state ticking; the dim window itself is derived below.
  useEffect(() => {
    const interval = setInterval(() => {
      const now = new Date();
      setMinutesNow(now.getHours() * 60 + now.getMinutes());
    }, DIM_TICK_MS);
    return () => clearInterval(interval);
  }, []);

  const dimActive = !!autoDim?.enabled && isInDimWindow(minutesNow, autoDim.start, autoDim.end);

  const toggleFullscreen = () => {
    try {
      if (document.fullscreenElement) void document.exitFullscreen();
      else void document.documentElement.requestFullscreen?.();
    } catch {
      // Some TV browsers refuse; they're usually fullscreen already.
    }
  };

  let content: React.ReactNode;
  if (notFound) {
    content = (
      <Box className="text-center">
        <Text as="p" className="text-2xl font-medium text-neutral-400">
          {t("notFoundTitle")}
        </Text>
        <Text as="p" className="mt-2 text-base text-neutral-500">
          {t("notFoundBody")}
        </Text>
      </Box>
    );
  } else if (config.data?.board_missing) {
    content = (
      <Box className="text-center">
        <Text as="p" className="text-2xl font-medium text-neutral-400">
          {t("boardMissingTitle")}
        </Text>
        <Text as="p" className="mt-2 text-base text-neutral-500">
          {t("boardMissingBody")}
        </Text>
      </Box>
    );
  } else if (config.data) {
    const rows = config.data.rows ?? 6;
    const cols = config.data.cols ?? 22;
    const deviceType = config.data.device_type ?? "flagship";
    content = (
      <PanelBoard
        message={frame.data?.message ?? null}
        animationsEnabled={config.data.animations_enabled ?? true}
        deviceType={deviceType}
        notesWide={deviceType === "note_array" ? Math.max(1, Math.round(cols / 15)) : 1}
        notesTall={deviceType === "note_array" ? Math.max(1, Math.round(rows / 3)) : 1}
        rows={rows}
        cols={cols}
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
    <Flex
      data-testid="panel-scene"
      data-panel-id={panelId}
      align="center"
      justify="center"
      className="fixed inset-0 overflow-hidden bg-black"
      style={{ cursor: cursorHidden ? "none" : undefined }}
      onClick={toggleFullscreen}
    >
      {content}
      {/* Auto-dim: slow-fading brightness overlay during the night window. */}
      <Box
        aria-hidden="true"
        data-testid="panel-dim"
        data-active={dimActive ? "true" : "false"}
        className="pointer-events-none absolute inset-0 bg-black"
        style={{ opacity: dimActive ? 0.65 : 0, transition: "opacity 5s ease" }}
      />
      {offline && (
        <Box
          data-testid="panel-offline"
          title={t("offline")}
          className="absolute right-4 bottom-4 size-2 rounded-full bg-amber-500/60"
        >
          <Text as="span" className="sr-only">
            {t("offline")}
          </Text>
        </Box>
      )}
    </Flex>
  );
}
