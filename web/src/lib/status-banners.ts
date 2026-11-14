/**
 * Which status banner a page shows (WEB-10; 07a `Web / Banner` `298:2280`,
 * 03 `33:126` "Honest hardware, one fix each").
 *
 * One banner at a time, the one whose fix comes first: a device with no
 * network cannot reach the hub; a hub that does not answer makes every board
 * fact stale; a display the hub cannot reach outranks a choice the user made
 * (pause, a Silence Schedule); a TV viewer comes last. Pure, so the order is
 * tested on its own; the host component reads the hub state and renders.
 *
 * A board that failed to start (`init-error`) is picked only with
 * `initError: true` (a display's own page). On Home the fleet-wide
 * BoardInitErrorBanner names every such board, including ones other than the
 * current one (#1829), so there a failed current board gets no second banner.
 * Either way, nothing else is said about a board that never started.
 */
import type { HealthSummary } from "@/lib/api";

/** A TV viewer's last show of a FiestaPanel (H13b `shown_panels`). */
export interface PanelLastShown {
  /** ISO instant. */
  at: string;
  /** The TV's device name, as it signed in ("Apple TV"). */
  deviceName: string;
}

export interface StatusBannerBoard {
  id: string;
  name: string;
  paused: boolean;
  /** Why the board failed to start (#1749), if it did. */
  error?: string | null;
  /** H12 per-display health; absent from a hub that predates it. */
  health?: HealthSummary | null;
  /**
   * FiestaPanel only (H13b). `undefined`: not a panel, or its viewers are not
   * known here (sign-in off, the HDMI display panel). `showing: false`: no
   * signed-in TV showed it recently; `lastShown` is the newest show, or null
   * if no TV ever did.
   */
  viewer?: { showing: true } | { showing: false; lastShown: PanelLastShown | null };
}

export interface StatusBannerSilence {
  active: boolean;
  /** When the window ends (ISO), if known. */
  until: string | null;
  /** The Silence Schedule's mode: `page` shows `pageName`; others keep or dim. */
  mode?: string;
  pageName?: string | null;
}

export interface StatusBannerInput {
  deviceOnline: boolean;
  hubReachable: boolean;
  /** When the hub last answered this browser (epoch ms), if ever. */
  lastHubContactAt: number | null;
  board?: StatusBannerBoard | null;
  silence?: StatusBannerSilence | null;
  /** Pick `init-error` for a board that failed to start (a display's own page). */
  initError?: boolean;
}

export type PickedStatusBanner =
  | { kind: "device-offline" }
  | { kind: "hub-unreachable"; lastContactAt: number | null }
  | { kind: "init-error"; board: StatusBannerBoard; error: string }
  | { kind: "display-offline"; board: StatusBannerBoard; lastConnectedAt: string | null }
  | { kind: "paused"; board: StatusBannerBoard }
  | { kind: "silenced"; board: StatusBannerBoard; silence: StatusBannerSilence }
  | { kind: "no-viewer"; board: StatusBannerBoard; lastShown: PanelLastShown | null };

export type PickedStatusBannerKind = PickedStatusBanner["kind"];

/** Whether H12 says the hub cannot reach this display right now. */
export function isDisplayOffline(health?: HealthSummary | null): boolean {
  if (!health) return false;
  return health.reachable === false || health.breaker_open === true;
}

/**
 * The one banner to show, or `null` for none. Kinds in `exclude` are skipped
 * (the next one down still shows), for a page that already says that state
 * some other way.
 */
export function pickStatusBanner(
  input: StatusBannerInput,
  exclude: ReadonlyArray<PickedStatusBannerKind> = [],
): PickedStatusBanner | null {
  const allowed = (kind: PickedStatusBannerKind) => !exclude.includes(kind);

  if (!input.deviceOnline) return allowed("device-offline") ? { kind: "device-offline" } : null;
  // Every board fact below came from the hub; while it does not answer they
  // are last known, not live, so none of them gets a banner of its own.
  if (!input.hubReachable) {
    return allowed("hub-unreachable") ? { kind: "hub-unreachable", lastContactAt: input.lastHubContactAt } : null;
  }

  const board = input.board;
  if (!board) return null;
  if (board.error) {
    return input.initError && allowed("init-error") ? { kind: "init-error", board, error: board.error } : null;
  }

  if (allowed("display-offline") && isDisplayOffline(board.health)) {
    return { kind: "display-offline", board, lastConnectedAt: board.health?.last_connected_at ?? null };
  }
  if (allowed("paused") && board.paused) return { kind: "paused", board };
  if (allowed("silenced") && input.silence?.active) return { kind: "silenced", board, silence: input.silence };
  if (allowed("no-viewer") && board.viewer && !board.viewer.showing) {
    return { kind: "no-viewer", board, lastShown: board.viewer.lastShown };
  }
  return null;
}

/** How recently a signed-in TV must have shown a panel to count as showing it. */
export const VIEWER_RECENT_MS = 5 * 60 * 1000;

/**
 * Whether a FiestaPanel has a viewer, from the signed-in TVs' `shown_panels`
 * (H13b). The hub records a view at most once a minute per TV, so "recent"
 * is a few of those. Browser kiosks and the `/p/display` HDMI output are
 * anonymous and never count.
 */
export function panelViewer(
  panelId: string,
  sessions: ReadonlyArray<{
    kind: string;
    device_name: string;
    shown_panels?: ReadonlyArray<{ panel_id: string; last_shown_at: string }>;
  }>,
  now: number,
): { showing: true } | { showing: false; lastShown: PanelLastShown | null } {
  let newest: PanelLastShown | null = null;
  let newestMs = -Infinity;
  for (const session of sessions) {
    if (session.kind !== "tv") continue;
    for (const shown of session.shown_panels ?? []) {
      if (shown.panel_id !== panelId) continue;
      const ms = Date.parse(shown.last_shown_at);
      if (Number.isNaN(ms) || ms <= newestMs) continue;
      newestMs = ms;
      newest = { at: shown.last_shown_at, deviceName: session.device_name };
    }
  }
  if (newest && now - newestMs <= VIEWER_RECENT_MS) return { showing: true };
  return { showing: false, lastShown: newest };
}
