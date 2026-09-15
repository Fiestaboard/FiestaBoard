import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AiApprovalCard } from "@/components/ai-approval-card";
import type { ToolCall } from "@/lib/ai-chat-types";

const DELETE_PAGE: ToolCall = {
  id: "c1",
  name: "delete_page",
  args: { page_id: "p1" },
  title: "Delete page",
  read_only: false,
  destructive: true,
  requires_approval: true,
  source: "mcp",
};

describe("AiApprovalCard", () => {
  it("names the call and puts focus on Deny, the safe answer", () => {
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={vi.fn()} onDeny={vi.fn()} />);
    expect(screen.getByRole("group", { name: /needs your approval/i })).toBeInTheDocument();
    expect(screen.getByText(/Delete page/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deny" })).toHaveFocus();
  });

  it("Approve and Deny call their handlers", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn();
    const onDeny = vi.fn();
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={onApprove} onDeny={onDeny} />);

    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Deny" }));

    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onDeny).toHaveBeenCalledTimes(1);
  });

  it("disables both buttons while the decision is in flight", () => {
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={vi.fn()} onDeny={vi.fn()} busy />);
    expect(screen.getByRole("button", { name: "Deny" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /working/i })).toBeDisabled();
  });

  it("falls back to a generic description for a tool it does not know", () => {
    render(
      <AiApprovalCard
        call={{ ...DELETE_PAGE, name: "obliterate_everything", title: "Obliterate everything" }}
        onApprove={vi.fn()}
        onDeny={vi.fn()}
      />,
    );
    expect(screen.getByText("Obliterate everything")).toBeInTheDocument();
    expect(screen.getByText(/cannot be undone by another tool/i)).toBeInTheDocument();
  });
});
