import type { SilenceScheduleConfig } from "@/lib/api";

/** The seven keys a per-board silence override may carry. */
const SILENCE_KEYS = [
  "enabled",
  "start_time",
  "end_time",
  "mode",
  "page_id",
  "indicator_text",
  "indicator_position",
] as const;

type SilenceLayer = Partial<SilenceScheduleConfig> & { by_board?: Record<string, Partial<SilenceScheduleConfig>> };

/**
 * Resolve the effective silence schedule for one board (issue #1788).
 *
 * Mirrors `resolve_silence_schedule()` in `src/config.py`: the top-level keys
 * of `features.silence_schedule` are the install-wide default, and
 * `by_board[boardId]` overrides them key by key. A board with no entry — or no
 * board at all — resolves to the install-wide values, so a newly added board
 * inherits the install's quiet hours instead of being unexpectedly loud.
 *
 * Normalization stays on the server; this only does the layering, so the form
 * shows exactly what was stored.
 */
export function resolveSilenceConfig(
  config: SilenceLayer | undefined | null,
  boardId?: string,
): Partial<SilenceScheduleConfig> {
  const { by_board: byBoard, ...base } = config ?? {};
  if (!boardId) return base;

  const entry = byBoard?.[boardId];
  if (!entry || typeof entry !== "object") return base;

  const resolved: Record<string, unknown> = { ...base };
  for (const key of SILENCE_KEYS) {
    if (key in entry) resolved[key] = entry[key];
  }
  return resolved as Partial<SilenceScheduleConfig>;
}
