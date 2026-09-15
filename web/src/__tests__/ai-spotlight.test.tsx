import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SpotlightProvider, useSpotlight } from "@/components/ai-spotlight/spotlight-provider";
import { ANCHOR_ATTR } from "@/lib/ai-choreography/anchors";

let api: ReturnType<typeof useSpotlight> | null = null;

function Probe() {
  api = useSpotlight();
  return null;
}

function renderWithAnchor() {
  const anchor = document.createElement("input");
  anchor.setAttribute(ANCHOR_ATTR, "settings.general.instance_name");
  document.body.appendChild(anchor);
  const utils = render(
    <SpotlightProvider>
      <Probe />
    </SpotlightProvider>,
  );
  return { ...utils, anchor };
}

describe("SpotlightProvider", () => {
  it("shows a ring on the anchor and a live caption, and hides both", () => {
    const { anchor } = renderWithAnchor();
    act(() => api!.show({ anchor: "settings.general.instance_name", caption: "Renaming…" }));
    expect(screen.getByTestId("ai-spotlight-ring")).toHaveAttribute("data-anchor", "settings.general.instance_name");
    const caption = screen.getByTestId("ai-spotlight-caption");
    expect(caption).toHaveAttribute("role", "status");
    expect(caption).toHaveTextContent("Renaming…");
    expect(api!.active).toBe(true);
    act(() => api!.caption("Saved", "landed"));
    expect(screen.getByTestId("ai-spotlight-caption")).toHaveTextContent("Saved");
    act(() => api!.hide());
    expect(screen.queryByTestId("ai-spotlight-ring")).toBeNull();
    anchor.remove();
  });

  it("wires Stop and Approve/Deny to the registered handlers", async () => {
    const user = userEvent.setup();
    const { anchor } = renderWithAnchor();
    const handlers = { onStop: vi.fn(), onApprove: vi.fn(), onDeny: vi.fn() };
    act(() => api!.setHandlers(handlers));
    act(() => api!.show({ anchor: "settings.general.instance_name", caption: "Working", controls: "stop" }));
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(handlers.onStop).toHaveBeenCalled();
    act(() => api!.show({ anchor: "settings.general.instance_name", caption: "Delete?", controls: "approval" }));
    await user.click(screen.getByRole("button", { name: "Deny" }));
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(handlers.onDeny).toHaveBeenCalled();
    expect(handlers.onApprove).toHaveBeenCalled();
    anchor.remove();
  });

  it("renders a replica ghost over a text input and a badge elsewhere, and clears them", () => {
    const { anchor } = renderWithAnchor();
    const toggle = document.createElement("button");
    toggle.setAttribute(ANCHOR_ATTR, "settings.display.reduce_motion");
    document.body.appendChild(toggle);
    act(() => {
      api!.ghost("settings.general.instance_name", "Kitchen", 0.5, "auto");
      api!.ghost("settings.display.reduce_motion", "On", 1, "auto");
    });
    const ghosts = screen.getAllByTestId("ai-ghost");
    expect(ghosts).toHaveLength(2);
    expect(ghosts[0].querySelector("[data-variant='replica']")).not.toBeNull();
    expect(ghosts[1].querySelector("[data-variant='badge']")).not.toBeNull();
    // A ghost for the same anchor updates in place rather than stacking.
    act(() => api!.ghost("settings.general.instance_name", "Kitchen", 1, "auto"));
    expect(screen.getAllByTestId("ai-ghost")).toHaveLength(2);
    act(() => api!.clearGhosts());
    expect(screen.queryAllByTestId("ai-ghost")).toHaveLength(0);
    anchor.remove();
    toggle.remove();
  });

  it("pulses the anchor with the landed class for a moment", () => {
    vi.useFakeTimers();
    try {
      const { anchor } = renderWithAnchor();
      act(() => api!.pulse("settings.general.instance_name"));
      expect(anchor.classList.contains("ai-anchor-pulse")).toBe(true);
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      expect(anchor.classList.contains("ai-anchor-pulse")).toBe(false);
      anchor.remove();
    } finally {
      vi.useRealTimers();
    }
  });
});
