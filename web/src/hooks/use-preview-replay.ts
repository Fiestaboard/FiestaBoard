"use client";

import { useCallback, useState } from "react";

type Phase = "idle" | "blank" | "armed" | "playing";

export interface PreviewReplay {
  /** What the board shows: the message, or a blank board while a replay starts. */
  message: string | null;
  /** Pass to the board's `animate`: on only while a replay plays. */
  animate: boolean;
  /** True from Replay until the next change to the message. */
  replaying: boolean;
  /** Play the split-flap cascade from a blank board to the current message. */
  replay: () => void;
}

/**
 * The editor's preview never flaps while you edit (owner decision D7,
 * BB-E-9): every change snaps. Replay plays the real cascade on demand.
 *
 * The kit flaps a tile only when its character changes while animations are
 * on, so a replay runs over three frames: blank the board with animations off
 * (it snaps to blank), switch animations on, then bring the message back so
 * every tile flaps from blank to its character. The next change to the
 * message ends the replay, so it snaps again.
 */
export function usePreviewReplay(message: string | null): PreviewReplay {
  const [state, setState] = useState<{ phase: Phase; of: string | null }>({ phase: "idle", of: message });

  // An edit ends the replay for good (a state adjustment during render, not an
  // effect), even if a later edit brings the same message back.
  if (state.phase !== "idle" && state.of !== message) setState({ phase: "idle", of: message });

  const replay = useCallback(() => {
    setState({ phase: "blank", of: message });
    const advance = (from: Phase, to: Phase) =>
      setState((current) => (current.phase === from ? { ...current, phase: to } : current));
    requestAnimationFrame(() => {
      advance("blank", "armed");
      requestAnimationFrame(() => advance("armed", "playing"));
    });
  }, [message]);

  const replaying = state.phase !== "idle" && state.of === message;
  if (!replaying) return { message, animate: false, replaying: false, replay };
  if (state.phase === "blank") return { message: "", animate: false, replaying, replay };
  if (state.phase === "armed") return { message: "", animate: true, replaying, replay };
  return { message, animate: true, replaying, replay };
}
