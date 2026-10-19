import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { groupTurns, ReadOnlyTranscript, TranscriptTurns } from "@/components/ai-chat-transcript";
import type { ChatMessage, Elicitation, ToolCallDisplay } from "@/lib/ai-chat-types";

function Wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function call(id: string, phase: ToolCallDisplay["phase"] = "ok"): ToolCallDisplay {
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
  };
}

function transcript(messages: ChatMessage[], props: Partial<React.ComponentProps<typeof TranscriptTurns>> = {}) {
  return (
    <TranscriptTurns
      turns={groupTurns(messages)}
      pendingApproval={null}
      pendingElicitation={null}
      busy={false}
      onApprove={vi.fn()}
      onAnswer={vi.fn()}
      {...props}
    />
  );
}

describe("assistant turn activity", () => {
  it("collapses work across model entries while keeping the final reply visible and the details chronological", async () => {
    const user = userEvent.setup();
    render(
      transcript([
        { role: "assistant", content: "First I checked your morning.", toolCalls: [call("one")] },
        { role: "assistant", content: "Then I checked your evening.", toolCalls: [call("two")] },
        { role: "assistant", content: "Your daily schedule is ready." },
      ]),
      { wrapper: Wrapper },
    );
    const activity = screen.getByTestId("ai-turn-activity");
    expect(activity).toHaveTextContent("2 actions completed");
    expect(screen.getByText("Your daily schedule is ready.")).toBeVisible();
    expect(screen.queryByText("First I checked your morning.")).not.toBeInTheDocument();
    await user.click(within(activity).getByRole("button"));
    const details = screen.getByTestId("ai-activity-details");
    expect(details).toHaveTextContent(
      /First I checked your morning\..*Add schedule.*Then I checked your evening\..*Add schedule/,
    );
    expect(within(details).getAllByTestId("ai-tool-create_schedule")).toHaveLength(2);
    expect(details).not.toHaveTextContent("Your daily schedule is ready.");
  });

  it("keeps approval actionable outside collapsed work even when the call is in an earlier entry", async () => {
    const user = userEvent.setup();
    const pending = {
      ...call("delete", "awaiting_approval"),
      name: "delete_page",
      destructive: true,
      requires_approval: true,
    };
    const onApprove = vi.fn();
    render(
      transcript(
        [
          { role: "assistant", content: "I can remove that page.", toolCalls: [pending] },
          { role: "assistant", content: "" },
        ],
        { pendingApproval: pending, onApprove },
      ),
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId("ai-turn-activity")).toHaveTextContent(/approval/i);
    const approve = screen.getByRole("button", { name: "Approve" });
    expect(approve.closest('[data-testid="ai-activity-details"]')).toBeNull();
    await user.click(approve);
    expect(onApprove).toHaveBeenCalledWith("delete", "approve");
  });

  it("keeps questions actionable outside collapsed work and disables them in saved history", async () => {
    const user = userEvent.setup();
    const question: Elicitation = {
      id: "q",
      name: "ask_user",
      message: "Which board?",
      allow_free_text: true,
      requested_schema: { type: "object", properties: { answer: { type: "string", enum: ["Kitchen", "Hall"] } } },
    };
    const messages: ChatMessage[] = [
      { role: "assistant", content: "I found two boards.", toolCalls: [call("one")], elicitation: question },
      { role: "assistant", content: "" },
    ];
    const onAnswer = vi.fn();
    const { unmount } = render(transcript(messages, { pendingElicitation: question, onAnswer }), { wrapper: Wrapper });
    const answer = screen.getByRole("button", { name: "Kitchen" });
    expect(answer.closest('[data-testid="ai-activity-details"]')).toBeNull();
    await user.click(answer);
    expect(onAnswer).toHaveBeenCalledWith("q", { action: "accept", content: { answer: "Kitchen" } });
    unmount();
    render(<ReadOnlyTranscript messages={messages} />, { wrapper: Wrapper });
    expect(screen.getByRole("button", { name: "Kitchen" })).toBeDisabled();
  });

  it("shows thinking before the first tool exists", () => {
    render(transcript([{ role: "assistant", content: "", pending: true }], { busy: true }), { wrapper: Wrapper });
    expect(screen.getByTestId("ai-turn-activity")).toHaveTextContent(/thinking/i);
    expect(screen.queryByText(/completed/)).not.toBeInTheDocument();
  });

  it("keeps the final reply visible when the stream stores prose and tool calls in the same entry", () => {
    render(transcript([{ role: "assistant", content: "Your schedule is ready.", toolCalls: [call("one")] }]), {
      wrapper: Wrapper,
    });
    expect(screen.getByText("Your schedule is ready.")).toBeVisible();
    expect(screen.queryByTestId("ai-tool-create_schedule")).not.toBeInTheDocument();
  });

  it("surfaces the latest successful artwork without promoting a later failed proposal", async () => {
    render(
      transcript([
        {
          role: "assistant",
          content: "Your artwork is ready.",
          toolCalls: [
            {
              ...call("one"),
              name: "create_page",
              appliedSnapshot: { name: "Sun", template: ["SUNSHINE"], line_metadata: [] },
            },
            {
              ...call("two", "error"),
              name: "update_page",
              appliedSnapshot: { name: "Rain", template: ["RAIN"], line_metadata: [] },
            },
          ],
        },
      ]),
      { wrapper: Wrapper },
    );
    const artwork = screen.getByTestId("ai-turn-artwork");
    expect(artwork.closest('[data-testid="ai-activity-details"]')).toBeNull();
    expect(await within(artwork).findByRole("img", { name: /SUNSHINE/ })).toBeVisible();
    expect(within(artwork).queryByRole("img", { name: /RAIN/ })).not.toBeInTheDocument();
  });

  it("does not label an unanswered saved question as finished", () => {
    render(
      <ReadOnlyTranscript
        messages={[
          {
            role: "assistant",
            content: "",
            elicitation: {
              id: "q",
              name: "ask_user",
              message: "Which board?",
              allow_free_text: true,
              requested_schema: { type: "object", properties: {} },
            },
          },
        ]}
      />,
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId("ai-turn-activity")).toHaveAttribute("data-activity", "input");
  });

  it("keeps failures and warnings visible when details are closed", () => {
    const failed = {
      ...call("failure", "error"),
      result: {
        id: "failure",
        name: "create_schedule",
        status: "error" as const,
        summary: "",
        result: null,
        error: "That schedule overlaps an existing entry.",
      },
    };
    render(
      transcript([
        {
          role: "assistant",
          content: "",
          toolCalls: [call("one"), failed],
          warnings: ["Some changes could not be applied."],
        },
      ]),
      { wrapper: Wrapper },
    );
    expect(screen.getByTestId("ai-turn-activity")).not.toHaveTextContent("Finished");
    expect(screen.getByText("That schedule overlaps an existing entry.")).toBeVisible();
    expect(screen.getByText("Some changes could not be applied.")).toBeVisible();
  });

  it.each(["denied", "stopped"] as const)("preserves the distinct %s outcome without calling it a failure", (phase) => {
    render(transcript([{ role: "assistant", content: "", toolCalls: [call("one", phase)] }]), { wrapper: Wrapper });
    const activity = screen.getByTestId("ai-turn-activity");
    expect(activity).toHaveTextContent(phase === "denied" ? /declined/i : /stopped/i);
    expect(activity).not.toHaveTextContent(/failed|error|finished/i);
  });
});
