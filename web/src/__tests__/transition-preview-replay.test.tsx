import { transitionsForModel, tryResolveDeviceModel } from "@fiestaboard/ui";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TransitionPreview } from "@/components/displays/transition-preview";

const model = tryResolveDeviceModel("divoom_pixoo64").model!;
const flip = transitionsForModel(model).find((entry) => entry.id === "flip")!;

function matrix() {
  return screen.getByTestId("transition-preview").querySelector("[data-slot='led-matrix-display']")!;
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

afterEach(() => {
  vi.useRealTimers();
  document.documentElement.classList.remove("reduce-motion");
});

describe("LED replay", () => {
  it("starts each replay from a newly settled layout then makes one device-adjusted change", async () => {
    vi.useFakeTimers();
    expect(flip.spec).toMatchObject({ kind: "flip", stepMs: 200, halfFlap: false });
    render(<TransitionPreview value="flip" model={model} spec={flip.spec!} />);
    const first = matrix();
    expect(first).toHaveAttribute("aria-label", expect.stringContaining("HELLO WORLD"));
    await advance(20_000);
    expect(first).toHaveAttribute("aria-label", expect.stringContaining("FIESTA BOARD"));

    fireEvent.click(screen.getByRole("button", { name: "Replay preview" }));
    const restarted = matrix();
    expect(restarted).not.toBe(first);
    expect(restarted).toHaveAttribute("aria-label", expect.stringContaining("HELLO WORLD"));
    expect(restarted).toHaveAttribute("data-transition", "flip");
    await advance(119);
    expect(restarted).toHaveAttribute("aria-label", expect.stringContaining("HELLO WORLD"));
    await advance(1);
    expect(restarted).toHaveAttribute("aria-label", expect.stringContaining("FIESTA BOARD"));
    await advance(20_000);
    expect(matrix()).toBe(restarted);
    expect(restarted).toHaveAttribute("aria-label", expect.stringContaining("FIESTA BOARD"));
  });

  it("settles the LED preview without animation or replay under reduced motion", async () => {
    vi.useFakeTimers();
    document.documentElement.classList.add("reduce-motion");
    render(<TransitionPreview value="flip" model={model} spec={flip.spec!} />);
    await advance(20_000);
    expect(matrix()).toHaveAttribute("data-transition", "none");
    expect(matrix()).toHaveAttribute("aria-label", expect.stringContaining("FIESTA BOARD"));
    expect(screen.getByRole("button", { name: "Replay preview" })).toBeDisabled();
  });
});
