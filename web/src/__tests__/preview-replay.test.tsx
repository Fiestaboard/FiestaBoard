/**
 * D7 (BB-E-9): the editor's preview never flaps while you edit; Replay plays
 * the real cascade on demand.
 *
 * - `BoardViewport animate={false}` hands the kit `animationsEnabled={false}`
 *   (tiles snap), and `animate` can never switch animations on against the
 *   user's own setting.
 * - `usePreviewReplay` blanks the board with animations off, arms them, then
 *   restores the message so the kit flaps every tile from blank. The next edit
 *   snaps again.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const kitViewport = vi.fn();
vi.mock("@fiestaboard/ui", async () => {
  const actual = await vi.importActual<typeof import("@fiestaboard/ui")>("@fiestaboard/ui");
  return {
    ...actual,
    BoardViewport: (props: { animationsEnabled?: boolean }) => {
      kitViewport(props);
      return <div data-testid="kit-viewport" data-animations={String(props.animationsEnabled)} />;
    },
  };
});

const animationsOn = vi.fn(() => true);
vi.mock("@/hooks/use-board-animations", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/use-board-animations")>("@/hooks/use-board-animations");
  return { ...actual, useBoardAnimationsEnabled: () => animationsOn() };
});

import { BoardViewport } from "@/components/board-viewport";
import { usePreviewReplay } from "@/hooks/use-preview-replay";

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  kitViewport.mockClear();
  animationsOn.mockReturnValue(true);
});

describe("BoardViewport animate", () => {
  it("follows the user's setting by default", () => {
    const { getByTestId } = render(<BoardViewport message="HI" deviceType="flagship" />, { wrapper });
    expect(getByTestId("kit-viewport")).toHaveAttribute("data-animations", "true");
  });

  it("snaps tiles when animate is false", () => {
    const { getByTestId } = render(<BoardViewport message="HI" deviceType="flagship" animate={false} />, {
      wrapper,
    });
    expect(getByTestId("kit-viewport")).toHaveAttribute("data-animations", "false");
  });

  it("never turns animations on against the user's setting", () => {
    animationsOn.mockReturnValue(false);
    const { getByTestId } = render(<BoardViewport message="HI" deviceType="flagship" animate />, { wrapper });
    expect(getByTestId("kit-viewport")).toHaveAttribute("data-animations", "false");
  });
});

describe("usePreviewReplay", () => {
  it("shows the message without animation while editing", () => {
    const { result } = renderHook(({ message }) => usePreviewReplay(message), {
      initialProps: { message: "HELLO" as string | null },
    });
    expect(result.current.message).toBe("HELLO");
    expect(result.current.animate).toBe(false);
    expect(result.current.replaying).toBe(false);
  });

  it("blanks, arms and then plays the message from blank", async () => {
    const frames: Array<[string | null, boolean]> = [];
    const { result } = renderHook(
      ({ message }) => {
        const replay = usePreviewReplay(message);
        frames.push([replay.message, replay.animate]);
        return replay;
      },
      { initialProps: { message: "HELLO" as string | null } },
    );
    frames.length = 0;
    act(() => result.current.replay());
    await waitFor(() => expect(result.current.animate).toBe(true));
    await waitFor(() => expect(result.current.message).toBe("HELLO"));
    // blank with animations off (snap to blank), blank armed, then the message animated
    expect(frames).toContainEqual(["", false]);
    expect(frames).toContainEqual(["", true]);
    const blankOff = frames.findIndex(([m, a]) => m === "" && !a);
    const armed = frames.findIndex(([m, a]) => m === "" && a);
    expect(armed).toBeGreaterThan(blankOff);
    expect(result.current.message).toBe("HELLO");
    expect(result.current.animate).toBe(true);
    expect(result.current.replaying).toBe(true);
  });

  it("the next edit snaps again", async () => {
    const { result, rerender } = renderHook(({ message }) => usePreviewReplay(message), {
      initialProps: { message: "HELLO" as string | null },
    });
    act(() => result.current.replay());
    await waitFor(() => expect(result.current.message).toBe("HELLO"));
    expect(result.current.animate).toBe(true);
    rerender({ message: "HELLO!" });
    expect(result.current.message).toBe("HELLO!");
    expect(result.current.animate).toBe(false);
    expect(result.current.replaying).toBe(false);
  });
});
