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
  system_gated: false,
  auto_approved: false,
};

const RESTART_SYSTEM: ToolCall = {
  ...DELETE_PAGE,
  id: "c2",
  name: "restart_system",
  args: {},
  title: "Restart system",
  system_gated: true,
};

const APPROVE_ALL = /approve and don.t ask again in this chat/i;

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

  // -- "Approve and don't ask again in this chat" (#2021) --

  it("offers 'don't ask again' for an ordinary destructive call and it approves through its own handler", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn();
    const onApproveAll = vi.fn();
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={onApprove} onDeny={vi.fn()} onApproveAll={onApproveAll} />);

    await user.click(screen.getByRole("button", { name: APPROVE_ALL }));

    expect(onApproveAll).toHaveBeenCalledTimes(1);
    expect(onApprove).not.toHaveBeenCalled();
  });

  it("does not offer 'don't ask again' for a system-gated call", () => {
    render(<AiApprovalCard call={RESTART_SYSTEM} onApprove={vi.fn()} onDeny={vi.fn()} onApproveAll={vi.fn()} />);
    expect(screen.queryByRole("button", { name: APPROVE_ALL })).not.toBeInTheDocument();
    // Approve / Deny are untouched for the system tier.
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deny" })).toHaveFocus();
  });

  it("keeps Deny as the mount focus when 'don't ask again' is offered", () => {
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={vi.fn()} onDeny={vi.fn()} onApproveAll={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Deny" })).toHaveFocus();
  });

  it("disables 'don't ask again' while the decision is in flight", () => {
    render(<AiApprovalCard call={DELETE_PAGE} onApprove={vi.fn()} onDeny={vi.fn()} onApproveAll={vi.fn()} busy />);
    expect(screen.getByRole("button", { name: APPROVE_ALL })).toBeDisabled();
  });
});
