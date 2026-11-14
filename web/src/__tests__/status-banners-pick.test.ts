/**
 * One status banner at a time, the one whose fix comes first (03 `33:126`).
 */
import { describe, expect, it } from "vitest";

import type { HealthSummary } from "@/lib/api";
import {
  isDisplayOffline,
  panelViewer,
  pickStatusBanner,
  type StatusBannerBoard,
  type StatusBannerInput,
  VIEWER_RECENT_MS,
} from "@/lib/status-banners";

const HEALTHY: HealthSummary = {
  last_connected_at: "2026-11-13T22:00:00+00:00",
  last_update_at: "2026-11-13T22:00:00+00:00",
  latency_ms: 40,
  last_error_at: null,
  last_error: null,
  reachable: true,
  breaker_open: false,
};

const OFFLINE: HealthSummary = {
  ...HEALTHY,
  last_connected_at: "2026-11-13T21:12:00+00:00",
  last_error_at: "2026-11-13T22:01:00+00:00",
  last_error: "unreachable",
  reachable: false,
};

function board(overrides: Partial<StatusBannerBoard> = {}): StatusBannerBoard {
  return { id: "kitchen", name: "Kitchen board", paused: false, health: HEALTHY, ...overrides };
}

function input(overrides: Partial<StatusBannerInput> = {}): StatusBannerInput {
  return {
    deviceOnline: true,
    hubReachable: true,
    lastHubContactAt: 1000,
    board: board(),
    silence: null,
    ...overrides,
  };
}

describe("pickStatusBanner", () => {
  it("shows nothing for a healthy board", () => {
    expect(pickStatusBanner(input())).toBeNull();
  });

  it("says this device is offline before anything else", () => {
    expect(pickStatusBanner(input({ deviceOnline: false, hubReachable: false }))).toEqual({ kind: "device-offline" });
  });

  it("says the hub is unreachable, with when it last answered, and hides stale board states", () => {
    const picked = pickStatusBanner(
      input({ hubReachable: false, lastHubContactAt: 42, board: board({ paused: true, health: OFFLINE }) }),
    );
    expect(picked).toEqual({ kind: "hub-unreachable", lastContactAt: 42 });
  });

  it("puts an offline display ahead of a pause", () => {
    const picked = pickStatusBanner(input({ board: board({ paused: true, health: OFFLINE }) }));
    expect(picked?.kind).toBe("display-offline");
    expect(picked).toMatchObject({ lastConnectedAt: "2026-11-13T21:12:00+00:00" });
  });

  it("treats a hub holding writes back as an offline display", () => {
    expect(pickStatusBanner(input({ board: board({ health: { ...HEALTHY, breaker_open: true } }) }))?.kind).toBe(
      "display-offline",
    );
  });

  it("never calls a display offline when health is unknown (null reachable, a FiestaPanel)", () => {
    expect(pickStatusBanner(input({ board: board({ health: { ...HEALTHY, reachable: null } }) }))).toBeNull();
    expect(pickStatusBanner(input({ board: board({ health: undefined }) }))).toBeNull();
  });

  it("shows paused ahead of silenced", () => {
    const picked = pickStatusBanner(
      input({ board: board({ paused: true }), silence: { active: true, until: "2026-11-14T14:30:00Z" } }),
    );
    expect(picked?.kind).toBe("paused");
  });

  it("shows silenced while a Silence Schedule is on", () => {
    const silence = { active: true, until: "2026-11-14T14:30:00Z" };
    expect(pickStatusBanner(input({ silence }))).toEqual({ kind: "silenced", board: board(), silence });
  });

  it("shows no-viewer for a panel no TV is showing, last of all", () => {
    const lastShown = { at: "2026-11-13T20:00:00Z", deviceName: "Apple TV" };
    const panel = board({ viewer: { showing: false, lastShown } });
    expect(pickStatusBanner(input({ board: panel }))).toEqual({ kind: "no-viewer", board: panel, lastShown });
    expect(pickStatusBanner(input({ board: panel, silence: { active: true, until: null } }))?.kind).toBe("silenced");
    expect(pickStatusBanner(input({ board: board({ viewer: { showing: true } }) }))).toBeNull();
  });

  it("leaves a board that failed to start to the init-error banner", () => {
    expect(pickStatusBanner(input({ board: board({ error: "Cloud key rejected", paused: true }) }))).toBeNull();
  });

  it("skips excluded kinds and falls through to the next", () => {
    const both = input({ board: board({ health: OFFLINE }), silence: { active: true, until: null } });
    expect(pickStatusBanner(both, ["display-offline"])?.kind).toBe("silenced");
    expect(pickStatusBanner(input({ silence: { active: true, until: null } }), ["silenced"])).toBeNull();
    expect(pickStatusBanner(input({ deviceOnline: false }), ["device-offline"])).toBeNull();
    expect(pickStatusBanner(input({ hubReachable: false }), ["hub-unreachable"])).toBeNull();
  });

  it("shows nothing board-specific without a board", () => {
    expect(pickStatusBanner(input({ board: null }))).toBeNull();
  });
});

describe("isDisplayOffline", () => {
  it("is false without health", () => {
    expect(isDisplayOffline(null)).toBe(false);
  });
});

describe("panelViewer", () => {
  const now = Date.parse("2026-11-13T22:00:00Z");
  const tv = (name: string, shown: { panel_id: string; last_shown_at: string }[], kind = "tv") => ({
    kind,
    device_name: name,
    shown_panels: shown,
  });

  it("is showing when a signed-in TV showed the panel recently", () => {
    const at = new Date(now - VIEWER_RECENT_MS + 1000).toISOString();
    expect(panelViewer("p1", [tv("Apple TV", [{ panel_id: "p1", last_shown_at: at }])], now)).toEqual({
      showing: true,
    });
  });

  it("names the newest TV to show it when none did recently", () => {
    const older = new Date(now - 3 * 60 * 60 * 1000).toISOString();
    const newer = new Date(now - 2 * 60 * 60 * 1000).toISOString();
    expect(
      panelViewer(
        "p1",
        [
          tv("Google TV", [{ panel_id: "p1", last_shown_at: older }]),
          tv("Apple TV", [
            { panel_id: "p2", last_shown_at: new Date(now).toISOString() },
            { panel_id: "p1", last_shown_at: newer },
          ]),
        ],
        now,
      ),
    ).toEqual({ showing: false, lastShown: { at: newer, deviceName: "Apple TV" } });
  });

  it("never counts a browser session, and has no last show when no TV ever showed it", () => {
    const at = new Date(now).toISOString();
    expect(panelViewer("p1", [tv("Chrome on macOS", [{ panel_id: "p1", last_shown_at: at }], "browser")], now)).toEqual(
      { showing: false, lastShown: null },
    );
    expect(panelViewer("p1", [{ kind: "tv", device_name: "Apple TV" }], now)).toEqual({
      showing: false,
      lastShown: null,
    });
  });

  it("ignores an unreadable instant", () => {
    expect(panelViewer("p1", [tv("Apple TV", [{ panel_id: "p1", last_shown_at: "garbage" }])], now)).toEqual({
      showing: false,
      lastShown: null,
    });
  });
});
