"use client";

import { useCallback, useEffect, useState } from "react";

type Phase = "idle" | "queued" | "blank" | "armed" | "playing";

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
 *
 * Replay pressed while the preview's render is still on its way (`loading`,
 * BB-E-33) waits for it and plays that message, instead of starting on
 * nothing and being snapped off. A blank page has nothing loading, so Replay
 * there plays the blank board and leaves nothing queued for the next edit.
 */
export function usePreviewReplay(
  message: string | null,
  { loading = false }: { loading?: boolean } = {},
): PreviewReplay {
  const [state, setState] = useState<{ phase: Phase; of: string | null }>({ phase: "idle", of: message });

  // A message change during render (a state adjustment, not an effect): the
  // first real message starts a queued replay; any other edit ends a replay
  // for good, even if a later edit brings the same message back.
  if (state.phase === "queued") {
    if (!loading) setState({ phase: "blank", of: message });
    else if (state.of !== message) setState({ phase: "queued", of: message });
  } else if (state.phase !== "idle" && state.of !== message) {
    setState({ phase: "idle", of: message });
  }

  // Blank → armed → playing, one frame apart.
  const phase = state.phase;
  useEffect(() => {
    const next: Partial<Record<Phase, Phase>> = { blank: "armed", armed: "playing" };
    const to = next[phase];
    if (!to) return;
    const frame = requestAnimationFrame(() =>
      setState((current) => (current.phase === phase ? { ...current, phase: to } : current)),
    );
    return () => cancelAnimationFrame(frame);
  }, [phase]);

  const replay = useCallback(() => {
    setState({ phase: loading ? "queued" : "blank", of: message });
  }, [message, loading]);

  const replaying = state.phase !== "idle" && state.phase !== "queued" && state.of === message;
  if (!replaying) return { message, animate: false, replaying: false, replay };
  if (state.phase === "blank") return { message: "", animate: false, replaying, replay };
  if (state.phase === "armed") return { message: "", animate: true, replaying, replay };
  return { message, animate: true, replaying, replay };
}
