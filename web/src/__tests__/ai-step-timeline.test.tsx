import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AiStepTimeline } from "@/components/ai-step-timeline";
import type { ChatMessage, ToolCallDisplay, ToolPhase } from "@/lib/ai-chat-types";

// The live list of steps sits above the conversation in a fixed-height
// drawer, so a twenty-step turn used to take twenty rows away from the
// transcript for as long as it ran. It is capped and scrolls instead, and
// the row that is running stays in view as the turn advances.

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function call(id: string, phase: ToolPhase): ToolCallDisplay {
  return {
    id,
    name: "create_schedule",
    args: {},
    title: "Add schedule",
    read_only: false,
    destructive: false,
    requires_approval: false,
    source: "mcp",
    phase,
  } as ToolCallDisplay;
}

/** One pending assistant entry carrying `count` calls, `done` of them finished. */
function turn(count: number, done: number): ChatMessage[] {
  const calls = Array.from({ length: count }, (_, i) =>
    call(`c${i}`, i < done ? "ok" : i === done ? "running" : "running"),
  );
  return [
    { role: "user", content: "set up my day" },
    {
      role: "assistant",
      content: "",
      pending: true,
      status: { phase: "tool_running", toolCallId: `c${done}` },
      toolCalls: calls,
    },
  ];
}

const scrollIntoView = vi.fn();

/**
 * jsdom has no layout, so every element measures 0 and nothing ever
 * overflows. The component only scrolls a list that actually overflows —
 * which is the behaviour under test — so the test supplies the measurement.
 */
function withOverflow(overflowing: boolean) {
  Object.defineProperty(HTMLElement.prototype, "scrollHeight", {
    configurable: true,
    get: () => (overflowing ? 400 : 0),
  });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get: () => (overflowing ? 76 : 0),
  });
}

beforeEach(() => {
  scrollIntoView.mockClear();
  Element.prototype.scrollIntoView = scrollIntoView;
  withOverflow(false);
});

describe("AiStepTimeline", () => {
  it("caps the list and scrolls it rather than growing with the turn", async () => {
    render(<AiStepTimeline messages={turn(12, 3)} />, { wrapper: Wrapper });
    const list = await screen.findByTestId("ai-step-list");
    // A cap plus its own scroll: the drawer's conversation keeps its room
    // however many steps a turn takes.
    expect(list.className).toMatch(/overflow-y-auto/);
    expect(list.className).toMatch(/max-h-/);
  });

  it("still tells the whole story in the heading, however many rows are on screen", async () => {
    render(<AiStepTimeline messages={turn(12, 3)} />, { wrapper: Wrapper });
    expect(await screen.findByTestId("ai-step-timeline")).toHaveTextContent("3 of 12 steps");
  });

  it("keeps the running step in view as the turn advances", async () => {
    withOverflow(true);
    const { rerender } = render(<AiStepTimeline messages={turn(12, 3)} />, { wrapper: Wrapper });
    await screen.findByTestId("ai-step-list");
    expect(scrollIntoView).toHaveBeenCalled();

    scrollIntoView.mockClear();
    rerender(
      <Wrapper>
        <AiStepTimeline messages={turn(12, 7)} />
      </Wrapper>,
    );
    expect(scrollIntoView).toHaveBeenCalled();
  });

  it("scrolls without animating when the viewer asked for less motion", async () => {
    withOverflow(true);
    document.documentElement.classList.add("reduce-motion");
    render(<AiStepTimeline messages={turn(12, 3)} />, { wrapper: Wrapper });
    await screen.findByTestId("ai-step-list");
    expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ behavior: "auto" }));
    document.documentElement.classList.remove("reduce-motion");
  });

  it("does not scroll a short turn that already fits", async () => {
    withOverflow(false);
    render(<AiStepTimeline messages={turn(2, 1)} />, { wrapper: Wrapper });
    await screen.findByTestId("ai-step-list");
    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});
