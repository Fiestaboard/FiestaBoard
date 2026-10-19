import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AiTurnActivity } from "@/components/ai-step-timeline";
import type { ChatMessage, ToolCallDisplay } from "@/lib/ai-chat-types";

const call: ToolCallDisplay = {
  id: "one",
  name: "create_page",
  title: "Create page",
  args: {},
  read_only: false,
  destructive: false,
  requires_approval: false,
  source: "mcp",
  phase: "running",
};

describe("AiTurnActivity", () => {
  it("exposes the running action while the chronological details remain collapsed", async () => {
    const user = userEvent.setup();
    render(
      <AiTurnActivity
        entries={[{ role: "assistant", content: "", pending: true, toolCalls: [call] }]}
        status="streaming"
      >
        <li>Tool arguments and result</li>
      </AiTurnActivity>,
    );
    const activity = screen.getByTestId("ai-turn-activity");
    expect(activity).toHaveTextContent(/Create page/);
    expect(screen.queryByText("Tool arguments and result")).not.toBeInTheDocument();
    await user.click(within(activity).getByRole("button"));
    expect(screen.getByText("Tool arguments and result")).toBeVisible();
  });

  it("counts only successful observed tools across all entries", () => {
    const entries: ChatMessage[] = [
      { role: "assistant", content: "", toolCalls: [{ ...call, phase: "ok" }] },
      {
        role: "assistant",
        content: "",
        toolCalls: [
          { ...call, id: "two", phase: "denied" },
          { ...call, id: "three", name: "ask_user", phase: "ok" },
          { ...call, id: "four", phase: "error" },
        ],
      },
    ];
    render(<AiTurnActivity entries={entries} status="idle" />);
    expect(screen.getByTestId("ai-turn-activity")).toHaveTextContent("1 action completed");
  });
});
