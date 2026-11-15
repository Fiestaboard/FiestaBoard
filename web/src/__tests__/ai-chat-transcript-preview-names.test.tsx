/**
 * Slice 2.4 (review S3): every FiestaBot board preview in a transcript is a
 * BoardViewport, and a scrolling one is a `region` landmark. Several turns
 * must not pile up identical "Board preview" landmarks (axe landmark-unique),
 * so each preview is named for its reply and, on a tool card, its step.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { groupTurns, TranscriptTurns } from "@/components/ai-chat-transcript";
import type { ChatMessage, CurrentPageSnapshot, ToolCallDisplay } from "@/lib/ai-chat-types";

import { server } from "./mocks/server";

beforeEach(() => {
  server.use(
    http.post("/api/templates/render", () => HttpResponse.json({ rendered: "HELLO", lines: ["HELLO"], line_count: 1 })),
  );
});

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const snapshot: CurrentPageSnapshot = {
  name: "Draft",
  template: ["HELLO"],
  line_metadata: [],
  device_type: "flagship",
};

function applied(id: string): ToolCallDisplay {
  return {
    id,
    name: "update_page",
    args: {},
    title: "Update page",
    read_only: false,
    destructive: false,
    requires_approval: false,
    source: "mcp",
    phase: "ok",
    appliedSnapshot: snapshot,
  };
}

function renderTranscript(messages: ChatMessage[]) {
  return render(
    <TranscriptTurns
      turns={groupTurns(messages)}
      pendingApproval={null}
      pendingElicitation={null}
      busy={false}
      onApprove={vi.fn()}
      onAnswer={vi.fn()}
    />,
    { wrapper: Wrapper },
  );
}

const labels = () =>
  screen.getAllByRole("group", { name: /^Board preview, reply/ }).map((el) => el.getAttribute("aria-label"));

describe("FiestaBot board preview names", () => {
  it("names each reply's artwork after the reply, so two turns never share a landmark name", async () => {
    renderTranscript([
      { role: "user", content: "Make a morning page" },
      { role: "assistant", content: "Here it is.", toolCalls: [applied("a")] },
      { role: "user", content: "Make it louder" },
      { role: "assistant", content: "Louder.", toolCalls: [applied("b")] },
    ]);

    await waitFor(() => expect(labels()).toEqual(["Board preview, reply 1", "Board preview, reply 2"]));
  });

  it("numbers tool-card previews by step across a turn's entries", async () => {
    const user = userEvent.setup();
    renderTranscript([
      { role: "assistant", content: "First draft.", toolCalls: [applied("one"), applied("two")] },
      { role: "assistant", content: "Second draft.", toolCalls: [applied("three"), applied("four")] },
      { role: "assistant", content: "Done." },
    ]);
    await user.click(within(screen.getByTestId("ai-turn-activity")).getByRole("button"));
    // Each tool card keeps its output (and its preview) folded until opened.
    for (const card of screen.getAllByTestId("ai-tool-update_page")) {
      await user.click(within(card).getAllByRole("button")[0]);
    }

    const all = labels();
    // The turn's artwork (the last applied call) is drawn once, under the reply;
    // its own card hides its preview, so no name repeats.
    expect(all).toContain("Board preview, reply 1");
    expect(all).toContain("Board preview, reply 1, step 1");
    expect(all).toContain("Board preview, reply 1, step 2");
    // The second entry numbers on from the first: its first card is step 3.
    expect(all).toContain("Board preview, reply 1, step 3");
    expect(new Set(all).size).toBe(all.length);
  });
});
