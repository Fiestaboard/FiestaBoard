/**
 * Regression tests for the in-place update overlay.
 *
 * The bug these pin down: the overlay used to infer everything from /version.
 * One failed poll flipped it to "restarting", and the very next successful
 * poll — even from the same, unchanged container — was read as "update
 * complete", so it reloaded the user back to Settings while `docker compose
 * pull` was still running. The update banner was of course still there
 * (nothing had been updated), and the real restart landed a minute later with
 * no explanation on screen.
 *
 * The overlay now believes only the fiestaupdater sidecar's own record of the
 * attempt, which lives in a separate container and therefore survives
 * FiestaBoard being recreated.
 */
import { act, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UpdateProvider, useUpdate } from "@/components/update-context";
import { api, type UpdateStatusResponse } from "@/lib/api";

const LS_KEY = "fb_updating";
const FROM_VERSION = "8.20.5";

/** A status payload with no verdict yet — the sidecar is still working. */
function status(overrides: Partial<UpdateStatusResponse> = {}): UpdateStatusResponse {
  return {
    updater_available: true,
    auto_update_enabled: false,
    auto_update_interval: "manual",
    managed_externally: false,
    profile: "docker",
    sidecar_url: "http://fiestaupdater:8765",
    last_check: null,
    last_update: null,
    last_update_status: "in_progress",
    last_update_action: "update",
    last_update_error: null,
    last_update_previous_digest: null,
    last_update_completed_at: null,
    ...overrides,
  };
}

let reload: ReturnType<typeof vi.fn>;

/** Kicks off an update as soon as it mounts, mirroring the Settings banner. */
function StartUpdateOnMount() {
  const { startUpdate } = useUpdate();
  useEffect(() => {
    startUpdate(FROM_VERSION);
  }, [startUpdate]);
  return null;
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  window.localStorage.clear();
  reload = vi.fn();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...window.location, reload },
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("UpdateOverlay", () => {
  it("keeps waiting through a transient API failure during the pull", async () => {
    // One blip — a 503 from nginx's @api_starting, or a request that timed out
    // while the box was busy pulling — must not be read as a restart.
    const getUpdateStatus = vi
      .spyOn(api, "getUpdateStatus")
      .mockRejectedValueOnce(new Error("API error: 503"))
      .mockResolvedValue(status());

    render(
      <UpdateProvider>
        <StartUpdateOnMount />
      </UpdateProvider>,
    );

    await advance(1500 + 2000 * 3);

    expect(getUpdateStatus).toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
    // Still on step one, not "Restarting".
    expect(screen.getByText("Pulling the latest image from Docker Hub…")).toBeInTheDocument();
  });

  it("only calls the restart done when the sidecar reports success", async () => {
    // Three consecutive failures = the container really is gone.
    const getUpdateStatus = vi
      .spyOn(api, "getUpdateStatus")
      .mockRejectedValueOnce(new Error("network"))
      .mockRejectedValueOnce(new Error("network"))
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValue(status({ last_update_status: "success" }));

    render(
      <UpdateProvider>
        <StartUpdateOnMount />
      </UpdateProvider>,
    );

    // Initial delay + three failing polls.
    await advance(1500 + 2000 * 2);
    expect(reload).not.toHaveBeenCalled();
    expect(screen.getByText("Restarting FiestaBoard…")).toBeInTheDocument();

    // Next poll returns the sidecar's success verdict.
    await advance(2000);
    expect(screen.getByText("Update complete. Reloading…")).toBeInTheDocument();
    expect(reload).not.toHaveBeenCalled();

    // …and only reloads after the hold.
    await advance(800);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(getUpdateStatus).toHaveBeenCalled();
  });

  it("surfaces a sidecar failure instead of reloading into the old version", async () => {
    vi.spyOn(api, "getUpdateStatus").mockResolvedValue(
      status({ last_update_status: "failed", last_update_error: "pull_failed" }),
    );

    render(
      <UpdateProvider>
        <StartUpdateOnMount />
      </UpdateProvider>,
    );

    await advance(1500 + 2000);

    expect(screen.getByText("Update didn't complete")).toBeInTheDocument();
    expect(screen.getByText("Reason: pull_failed")).toBeInTheDocument();
    expect(reload).not.toHaveBeenCalled();
    // The attempt is over — nothing left to resume on the next page load.
    expect(window.localStorage.getItem(LS_KEY)).toBeNull();
  });

  it("hands the reload off to BootGate instead of clearing the marker", async () => {
    vi.spyOn(api, "getUpdateStatus").mockResolvedValue(status({ last_update_status: "success" }));

    render(
      <UpdateProvider>
        <StartUpdateOnMount />
      </UpdateProvider>,
    );

    await advance(1500 + 2000 + 800);

    expect(reload).toHaveBeenCalledTimes(1);
    const persisted = JSON.parse(window.localStorage.getItem(LS_KEY) ?? "{}");
    expect(persisted.awaitingBoot).toBe(true);
    expect(persisted.fromVersion).toBe(FROM_VERSION);
  });

  it("does not re-show the overlay after the post-update reload", async () => {
    // The reload loop this guards against: resuming the overlay here would see
    // "success" again and reload again, forever.
    window.localStorage.setItem(
      LS_KEY,
      JSON.stringify({ fromVersion: FROM_VERSION, startedAt: Date.now(), awaitingBoot: true }),
    );
    const getUpdateStatus = vi
      .spyOn(api, "getUpdateStatus")
      .mockResolvedValue(status({ last_update_status: "success" }));

    function ShowsFlag() {
      const { isUpdating, awaitingPostUpdateBoot } = useUpdate();
      return (
        <div>
          <span data-testid="updating">{String(isUpdating)}</span>
          <span data-testid="awaiting">{String(awaitingPostUpdateBoot)}</span>
        </div>
      );
    }

    render(
      <UpdateProvider>
        <ShowsFlag />
      </UpdateProvider>,
    );

    await advance(1500 + 2000 * 3);

    expect(screen.getByTestId("updating")).toHaveTextContent("false");
    expect(screen.getByTestId("awaiting")).toHaveTextContent("true");
    expect(getUpdateStatus).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
  });

  it("ignores a stale awaiting-boot marker", async () => {
    window.localStorage.setItem(
      LS_KEY,
      JSON.stringify({ fromVersion: FROM_VERSION, startedAt: Date.now() - 6 * 60 * 1000, awaitingBoot: true }),
    );

    function ShowsFlag() {
      const { awaitingPostUpdateBoot } = useUpdate();
      return <span data-testid="awaiting">{String(awaitingPostUpdateBoot)}</span>;
    }

    render(
      <UpdateProvider>
        <ShowsFlag />
      </UpdateProvider>,
    );

    await advance(100);

    expect(screen.getByTestId("awaiting")).toHaveTextContent("false");
  });
});
